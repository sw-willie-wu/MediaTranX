"""Tests for GeminiProvider.chat_completions_stream() generator.

Covers:
- Plain text stream: yields N OpenAI-compat content chunks + final usage
- functionCall: yields tool_calls in OpenAI-compat shape with synthetic ids
- Mixed text + functionCall in same chunk: yields both delta types
- Malformed JSON: skipped with warning
- HTTPError: raises RemoteApiError (mapped via _parse_error)
- abort_hook called immediately after urlopen
- Response closed in finally block
- Payload wiring: systemInstruction + tools forwarded correctly
- No content: empty candidates skipped gracefully
"""
import json
import logging
from unittest.mock import MagicMock, patch

import pytest


# ── helpers ──────────────────────────────────────────────────────────────────

def _make_sse_response(*lines: bytes):
    """Build a MagicMock HTTP response that iterates over the given byte lines."""
    resp = MagicMock(name="HTTPResponse")
    resp.__iter__ = lambda self: iter(list(lines))
    resp.__enter__ = MagicMock(return_value=resp)
    resp.__exit__ = MagicMock(return_value=False)
    resp.close = MagicMock()
    return resp


def _gemini_text_line(text: str) -> bytes:
    obj = {"candidates": [{"content": {"parts": [{"text": text}]}}]}
    return f"data: {json.dumps(obj)}\n".encode()


def _gemini_fc_line(name: str, args: dict) -> bytes:
    obj = {"candidates": [{"content": {"parts": [{"functionCall": {"name": name, "args": args}}]}}]}
    return f"data: {json.dumps(obj)}\n".encode()


def _gemini_usage_line(prompt: int = 10, candidates: int = 5, total: int = 15) -> bytes:
    obj = {"usageMetadata": {
        "promptTokenCount": prompt,
        "candidatesTokenCount": candidates,
        "totalTokenCount": total,
    }}
    return f"data: {json.dumps(obj)}\n".encode()


def _gemini_usage_with_text_line(text: str, prompt: int = 10, candidates: int = 5) -> bytes:
    """Gemini sometimes sends usageMetadata on the same chunk as the final text."""
    obj = {
        "candidates": [{"content": {"parts": [{"text": text}]}}],
        "usageMetadata": {
            "promptTokenCount": prompt,
            "candidatesTokenCount": candidates,
            "totalTokenCount": prompt + candidates,
        },
    }
    return f"data: {json.dumps(obj)}\n".encode()


def _prov():
    from app.adapters.ai.remote.gemini import GeminiProvider
    return GeminiProvider("https://generativelanguage.googleapis.com", "AIza-test")


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestGeminiChatCompletionsStream:

    def test_plain_text_stream_yields_content_chunks(self):
        """Each text part yields one OpenAI-compat content delta chunk."""
        lines = [
            _gemini_text_line("Hello"),
            _gemini_text_line(" world"),
        ]
        with patch(
            "app.adapters.ai.remote._http.urlopen",
            return_value=_make_sse_response(*lines),
        ):
            chunks = list(_prov().chat_completions_stream(
                model="gemini-2.5-flash",
                messages=[{"role": "user", "content": "hi"}],
            ))
        text_chunks = [c for c in chunks if c.get("choices") and c["choices"][0]["delta"].get("content")]
        assert len(text_chunks) == 2
        assert text_chunks[0]["choices"][0]["delta"]["content"] == "Hello"
        assert text_chunks[1]["choices"][0]["delta"]["content"] == " world"

    def test_usage_chunk_emitted_at_end(self):
        """usageMetadata is translated to a final usage chunk."""
        lines = [
            _gemini_text_line("x"),
            _gemini_usage_line(prompt=20, candidates=8, total=28),
        ]
        with patch(
            "app.adapters.ai.remote._http.urlopen",
            return_value=_make_sse_response(*lines),
        ):
            chunks = list(_prov().chat_completions_stream(
                model="gemini-2.5-flash",
                messages=[{"role": "user", "content": "hi"}],
            ))
        usage_chunks = [c for c in chunks if "usage" in c]
        assert len(usage_chunks) == 1
        assert usage_chunks[0]["usage"]["prompt_tokens"] == 20
        assert usage_chunks[0]["usage"]["completion_tokens"] == 8
        assert usage_chunks[0]["usage"]["total_tokens"] == 28

    def test_function_call_yields_openai_compat_tool_call(self):
        """functionCall part is translated to an OpenAI-compat tool_calls delta."""
        lines = [
            _gemini_fc_line("navigate_to", {"route": "/video"}),
        ]
        with patch(
            "app.adapters.ai.remote._http.urlopen",
            return_value=_make_sse_response(*lines),
        ):
            chunks = list(_prov().chat_completions_stream(
                model="gemini-2.5-flash",
                messages=[{"role": "user", "content": "go to video"}],
                tools=[{
                    "name": "navigate_to",
                    "description": "Navigate to a route",
                    "parameters": {"type": "object", "properties": {}},
                }],
            ))
        tc_chunks = [
            c for c in chunks
            if c.get("choices") and c["choices"][0]["delta"].get("tool_calls")
        ]
        assert len(tc_chunks) == 1
        tc = tc_chunks[0]["choices"][0]["delta"]["tool_calls"][0]
        assert tc["index"] == 0
        assert tc["function"]["name"] == "navigate_to"
        parsed_args = json.loads(tc["function"]["arguments"])
        assert parsed_args == {"route": "/video"}
        # Synthetic id must be present
        assert tc["id"].startswith("gemini-tc-")

    def test_multiple_function_calls_get_distinct_indices(self):
        """Each functionCall part gets a different index and synthetic id."""
        lines = [
            _gemini_fc_line("tool_a", {"a": 1}),
            _gemini_fc_line("tool_b", {"b": 2}),
        ]
        with patch(
            "app.adapters.ai.remote._http.urlopen",
            return_value=_make_sse_response(*lines),
        ):
            chunks = list(_prov().chat_completions_stream(
                model="gemini-2.5-flash",
                messages=[{"role": "user", "content": "call both"}],
            ))
        tc_chunks = [
            c for c in chunks
            if c.get("choices") and c["choices"][0]["delta"].get("tool_calls")
        ]
        assert len(tc_chunks) == 2
        indices = [c["choices"][0]["delta"]["tool_calls"][0]["index"] for c in tc_chunks]
        assert indices == [0, 1]
        ids = [c["choices"][0]["delta"]["tool_calls"][0]["id"] for c in tc_chunks]
        assert ids[0] != ids[1]

    def test_mixed_text_and_function_call_in_same_chunk(self):
        """A single SSE chunk with both text and functionCall yields two separate events."""
        chunk_data = {
            "candidates": [{
                "content": {
                    "parts": [
                        {"text": "Calling tool now."},
                        {"functionCall": {"name": "do_thing", "args": {"x": 42}}},
                    ]
                }
            }]
        }
        lines = [f"data: {json.dumps(chunk_data)}\n".encode()]
        with patch(
            "app.adapters.ai.remote._http.urlopen",
            return_value=_make_sse_response(*lines),
        ):
            chunks = list(_prov().chat_completions_stream(
                model="gemini-2.5-flash",
                messages=[{"role": "user", "content": "go"}],
            ))
        content_chunks = [
            c for c in chunks
            if c.get("choices") and c["choices"][0]["delta"].get("content")
        ]
        tc_chunks = [
            c for c in chunks
            if c.get("choices") and c["choices"][0]["delta"].get("tool_calls")
        ]
        assert len(content_chunks) == 1
        assert content_chunks[0]["choices"][0]["delta"]["content"] == "Calling tool now."
        assert len(tc_chunks) == 1
        assert tc_chunks[0]["choices"][0]["delta"]["tool_calls"][0]["function"]["name"] == "do_thing"

    def test_malformed_json_skipped_with_warning(self, caplog):
        """Non-parseable SSE data lines emit a warning and are skipped."""
        lines = [
            b"data: {this is not json}\n",
            _gemini_text_line("ok"),
        ]
        with caplog.at_level(logging.WARNING, logger="app.adapters.ai.remote.gemini"):
            with patch(
                "app.adapters.ai.remote._http.urlopen",
                return_value=_make_sse_response(*lines),
            ):
                chunks = list(_prov().chat_completions_stream(
                    model="gemini-2.5-flash",
                    messages=[{"role": "user", "content": "hi"}],
                ))
        text_chunks = [
            c for c in chunks
            if c.get("choices") and c["choices"][0]["delta"].get("content")
        ]
        assert len(text_chunks) == 1
        assert text_chunks[0]["choices"][0]["delta"]["content"] == "ok"
        assert any("malformed" in r.message.lower() for r in caplog.records)

    def test_http_error_raises_remote_api_error(self):
        """HTTPError from urlopen raises RemoteApiError before any chunks."""
        import urllib.error
        from app.handler.exceptions import RemoteApiError

        def fake_urlopen(req, timeout=None):
            err = urllib.error.HTTPError(
                req.full_url, 403, "Forbidden", {}, None,
            )
            err.read = lambda: b'{"error": {"status": "PERMISSION_DENIED"}}'
            raise err

        with patch(
            "app.adapters.ai.remote._http.urlopen",
            side_effect=fake_urlopen,
        ):
            with pytest.raises(RemoteApiError) as exc_info:
                list(_prov().chat_completions_stream(
                    model="gemini-2.5-flash",
                    messages=[{"role": "user", "content": "hi"}],
                ))
        assert exc_info.value.code in ("auth_failed", "remote_error")

    def test_abort_hook_called_after_urlopen(self):
        """abort_hook receives the response object immediately after urlopen returns."""
        lines = [_gemini_text_line("x")]
        resp = _make_sse_response(*lines)
        hook_received = []

        with patch(
            "app.adapters.ai.remote._http.urlopen",
            return_value=resp,
        ):
            list(_prov().chat_completions_stream(
                model="gemini-2.5-flash",
                messages=[{"role": "user", "content": "hi"}],
                abort_hook=lambda r: hook_received.append(r),
            ))
        assert len(hook_received) == 1
        assert hook_received[0] is resp

    def test_resp_closed_after_iteration(self):
        """Response.close() is always called in the finally block."""
        lines = [_gemini_text_line("hi")]
        resp = _make_sse_response(*lines)
        with patch(
            "app.adapters.ai.remote._http.urlopen",
            return_value=resp,
        ):
            list(_prov().chat_completions_stream(
                model="gemini-2.5-flash",
                messages=[{"role": "user", "content": "hi"}],
            ))
        resp.close.assert_called_once()

    def test_system_instruction_in_payload(self):
        """System message is forwarded as systemInstruction in the request payload."""
        captured: dict = {}

        def fake_urlopen(req, timeout=None):
            captured["payload"] = json.loads(req.data.decode("utf-8"))
            return _make_sse_response()

        messages = [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "hi"},
        ]
        with patch(
            "app.adapters.ai.remote._http.urlopen",
            side_effect=fake_urlopen,
        ):
            list(_prov().chat_completions_stream(
                model="gemini-2.5-flash",
                messages=messages,
            ))
        p = captured["payload"]
        assert "systemInstruction" in p
        assert p["systemInstruction"]["parts"][0]["text"] == "You are a helpful assistant."
        # System message must NOT be in contents
        assert all(c.get("role") != "system" for c in p["contents"])

    def test_tools_forwarded_as_function_declarations(self):
        """tools are converted to Gemini functionDeclarations in the request payload."""
        captured: dict = {}

        def fake_urlopen(req, timeout=None):
            captured["payload"] = json.loads(req.data.decode("utf-8"))
            return _make_sse_response()

        tools = [{
            "name": "my_tool",
            "description": "A test tool",
            "parameters": {"type": "object", "properties": {}},
        }]
        with patch(
            "app.adapters.ai.remote._http.urlopen",
            side_effect=fake_urlopen,
        ):
            list(_prov().chat_completions_stream(
                model="gemini-2.5-flash",
                messages=[{"role": "user", "content": "hi"}],
                tools=tools,
            ))
        p = captured["payload"]
        assert "tools" in p
        decls = p["tools"][0]["functionDeclarations"]
        assert len(decls) == 1
        assert decls[0]["name"] == "my_tool"

    def test_no_tools_no_tools_key_in_payload(self):
        """When tools=None, no 'tools' key is present in the payload."""
        captured: dict = {}

        def fake_urlopen(req, timeout=None):
            captured["payload"] = json.loads(req.data.decode("utf-8"))
            return _make_sse_response()

        with patch(
            "app.adapters.ai.remote._http.urlopen",
            side_effect=fake_urlopen,
        ):
            list(_prov().chat_completions_stream(
                model="gemini-2.5-flash",
                messages=[{"role": "user", "content": "hi"}],
                tools=None,
            ))
        assert "tools" not in captured["payload"]

    def test_empty_candidates_skipped_gracefully(self):
        """Chunks with no candidates produce no output (no crash)."""
        chunk_no_cand = json.dumps({"usageMetadata": {"promptTokenCount": 5}})
        lines = [
            f"data: {chunk_no_cand}\n".encode(),
            _gemini_text_line("done"),
        ]
        with patch(
            "app.adapters.ai.remote._http.urlopen",
            return_value=_make_sse_response(*lines),
        ):
            chunks = list(_prov().chat_completions_stream(
                model="gemini-2.5-flash",
                messages=[{"role": "user", "content": "hi"}],
            ))
        # Should have 1 text chunk + 1 usage chunk
        text_chunks = [
            c for c in chunks
            if c.get("choices") and c["choices"][0]["delta"].get("content")
        ]
        assert len(text_chunks) == 1

    def test_all_chunks_share_same_message_id(self):
        """All yielded chunks from a single call share the same 'id' prefix."""
        lines = [
            _gemini_text_line("A"),
            _gemini_text_line("B"),
        ]
        with patch(
            "app.adapters.ai.remote._http.urlopen",
            return_value=_make_sse_response(*lines),
        ):
            chunks = list(_prov().chat_completions_stream(
                model="gemini-2.5-flash",
                messages=[{"role": "user", "content": "hi"}],
            ))
        ids = {c["id"] for c in chunks if "id" in c}
        assert len(ids) == 1  # All same message id
        assert next(iter(ids)).startswith("gemini-")
