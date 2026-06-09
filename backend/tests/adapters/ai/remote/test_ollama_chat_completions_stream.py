"""Tests for OllamaProvider.chat_completions_stream() and OQ-7 tool template probe.

Covers:
- Happy path: text delta chunks
- Tool-call delta chunks
- HTTPError raises RuntimeError before any chunks are yielded
- Malformed JSON lines are skipped with a warning
- [DONE] terminator stops the generator
- abort_hook invoked immediately after urlopen
- resp.close() called in finally
- No Authorization header when api_key is absent
- Authorization header present when api_key is set
- /v1/chat/completions endpoint used (not /api/chat)
- Payload contains stream:True, stream_options, tools, tool_choice

OQ-7 tool template probe (_supports_tools):
- Returns True when template contains "tools" marker
- Returns False when template has no tool-related markers
- Returns False on network/connection failure
- _detect_capabilities includes "tools" via template probe in fallback path
"""
import json
import logging
from unittest.mock import MagicMock, patch

import pytest

PATCH_TARGET = "app.adapters.ai.remote._http.urlopen"


# ── SSE response helpers ─────────────────────────────────────────────────────

def _make_sse_response(*lines: bytes):
    """Build a MagicMock HTTP response whose __iter__ returns the given byte lines."""
    resp = MagicMock(name="HTTPResponse")
    resp.__iter__ = lambda self: iter(list(lines))
    resp.__enter__ = MagicMock(return_value=resp)
    resp.__exit__ = MagicMock(return_value=False)
    resp.close = MagicMock()
    return resp


def _delta_line(text: str, chunk_id: str = "c1") -> bytes:
    obj = {"id": chunk_id, "choices": [{"delta": {"content": text}}]}
    return f"data: {json.dumps(obj)}\n".encode()


def _tool_line(index: int, tc_id: str, name: str, args: str) -> bytes:
    obj = {
        "id": "c1",
        "choices": [{
            "delta": {
                "tool_calls": [{
                    "index": index,
                    "id": tc_id,
                    "function": {"name": name, "arguments": args},
                }]
            }
        }],
    }
    return f"data: {json.dumps(obj)}\n".encode()


def _usage_line(prompt: int = 10, completion: int = 5) -> bytes:
    obj = {"usage": {"prompt_tokens": prompt, "completion_tokens": completion}}
    return f"data: {json.dumps(obj)}\n".encode()


DONE_LINE = b"data: [DONE]\n"


# ── chat_completions_stream tests ─────────────────────────────────────────────

class TestChatCompletionsStream:

    def _prov(self, api_key=None):
        from app.adapters.ai.remote.ollama import OllamaProvider
        return OllamaProvider("http://localhost:11434", api_key)

    def test_happy_path_text_chunks(self):
        """Yields raw chunk dicts for each text delta; [DONE] stops the generator."""
        lines = [
            _delta_line("Hello", "msg1"),
            _delta_line(" world", "msg1"),
            DONE_LINE,
        ]
        with patch(PATCH_TARGET, return_value=_make_sse_response(*lines)):
            chunks = list(self._prov().chat_completions_stream(
                model="qwen3:8b",
                messages=[{"role": "user", "content": "hi"}],
            ))
        assert len(chunks) == 2
        assert chunks[0]["choices"][0]["delta"]["content"] == "Hello"
        assert chunks[1]["choices"][0]["delta"]["content"] == " world"

    def test_usage_chunk_yielded(self):
        """Final usage chunk is yielded so caller can capture token counts."""
        lines = [_delta_line("x"), _usage_line(prompt=20, completion=3), DONE_LINE]
        with patch(PATCH_TARGET, return_value=_make_sse_response(*lines)):
            chunks = list(self._prov().chat_completions_stream(
                model="qwen3:8b",
                messages=[{"role": "user", "content": "hi"}],
            ))
        usage_chunks = [c for c in chunks if "usage" in c]
        assert len(usage_chunks) == 1
        assert usage_chunks[0]["usage"]["prompt_tokens"] == 20

    def test_tool_call_deltas_yielded(self):
        """Tool-call deltas are yielded as raw chunks (no normalization needed)."""
        lines = [
            _tool_line(0, "tc1", "navigate_to", '{"route":"/video"}'),
            DONE_LINE,
        ]
        with patch(PATCH_TARGET, return_value=_make_sse_response(*lines)):
            chunks = list(self._prov().chat_completions_stream(
                model="qwen3:8b",
                messages=[{"role": "user", "content": "go to video"}],
                tools=[{"name": "navigate_to", "description": "nav", "parameters": {}}],
            ))
        assert len(chunks) == 1
        tc = chunks[0]["choices"][0]["delta"]["tool_calls"][0]
        assert tc["function"]["name"] == "navigate_to"
        assert '"/video"' in tc["function"]["arguments"]

    def test_http_error_raises_runtime_error(self):
        """HTTPError from urlopen raises RuntimeError before any chunks are yielded."""
        import urllib.error

        def fake_urlopen(req, timeout=None):
            import io
            raise urllib.error.HTTPError(
                req.full_url, 401,
                "Unauthorized", {}, io.BytesIO(b"bad token"),
            )

        with patch(PATCH_TARGET, side_effect=fake_urlopen):
            with pytest.raises(RuntimeError, match="ollama API error 401"):
                list(self._prov().chat_completions_stream(
                    model="qwen3:8b",
                    messages=[{"role": "user", "content": "hi"}],
                ))

    def test_malformed_json_skipped_with_warning(self, caplog):
        """Non-parseable JSON data lines emit a warning and are skipped."""
        lines = [
            b"data: {this is not json}\n",
            _delta_line("ok"),
            DONE_LINE,
        ]
        with caplog.at_level(logging.WARNING, logger="app.adapters.ai.remote.ollama"):
            with patch(PATCH_TARGET, return_value=_make_sse_response(*lines)):
                chunks = list(self._prov().chat_completions_stream(
                    model="qwen3:8b",
                    messages=[{"role": "user", "content": "hi"}],
                ))
        assert len(chunks) == 1
        assert chunks[0]["choices"][0]["delta"]["content"] == "ok"
        assert any("malformed" in r.message.lower() for r in caplog.records)

    def test_done_terminator_stops_iteration(self):
        """[DONE] terminates the generator; lines after it must be ignored."""
        lines = [
            _delta_line("a"),
            DONE_LINE,
            _delta_line("should_not_appear"),
        ]
        with patch(PATCH_TARGET, return_value=_make_sse_response(*lines)):
            chunks = list(self._prov().chat_completions_stream(
                model="qwen3:8b",
                messages=[{"role": "user", "content": "hi"}],
            ))
        assert len(chunks) == 1
        assert chunks[0]["choices"][0]["delta"]["content"] == "a"

    def test_abort_hook_called_after_urlopen(self):
        """abort_hook receives the response object immediately after urlopen returns."""
        lines = [DONE_LINE]
        resp = _make_sse_response(*lines)
        hook_received = []

        with patch(PATCH_TARGET, return_value=resp):
            list(self._prov().chat_completions_stream(
                model="qwen3:8b",
                messages=[{"role": "user", "content": "hi"}],
                abort_hook=lambda r: hook_received.append(r),
            ))
        assert len(hook_received) == 1
        assert hook_received[0] is resp

    def test_resp_close_called_in_finally(self):
        """Response.close() is always called in the finally block."""
        lines = [_delta_line("x"), DONE_LINE]
        resp = _make_sse_response(*lines)
        with patch(PATCH_TARGET, return_value=resp):
            list(self._prov().chat_completions_stream(
                model="qwen3:8b",
                messages=[{"role": "user", "content": "hi"}],
            ))
        resp.close.assert_called_once()

    def test_no_auth_header_when_no_api_key(self):
        """Authorization header must be absent when api_key is not set."""
        lines = [DONE_LINE]
        captured: dict = {}

        def fake_urlopen(req, timeout=None):
            captured["headers"] = dict(req.headers)
            return _make_sse_response(*lines)

        with patch(PATCH_TARGET, side_effect=fake_urlopen):
            list(self._prov(api_key=None).chat_completions_stream(
                model="qwen3:8b",
                messages=[{"role": "user", "content": "hi"}],
            ))
        # urllib lowercases header names
        assert "authorization" not in {k.lower() for k in captured["headers"]}

    def test_auth_header_present_when_api_key_set(self):
        """Authorization header is forwarded when api_key is set."""
        lines = [DONE_LINE]
        captured: dict = {}

        def fake_urlopen(req, timeout=None):
            captured["headers"] = dict(req.headers)
            return _make_sse_response(*lines)

        with patch(PATCH_TARGET, side_effect=fake_urlopen):
            list(self._prov(api_key="my-token").chat_completions_stream(
                model="qwen3:8b",
                messages=[{"role": "user", "content": "hi"}],
            ))
        headers_lower = {k.lower(): v for k, v in captured["headers"].items()}
        assert "authorization" in headers_lower
        assert headers_lower["authorization"] == "Bearer my-token"

    def test_endpoint_uses_v1_chat_completions(self):
        """URL must be /v1/chat/completions (OpenAI-compat), not /api/chat."""
        lines = [DONE_LINE]
        captured: dict = {}

        def fake_urlopen(req, timeout=None):
            captured["url"] = req.full_url
            return _make_sse_response(*lines)

        with patch(PATCH_TARGET, side_effect=fake_urlopen):
            list(self._prov().chat_completions_stream(
                model="qwen3:8b",
                messages=[{"role": "user", "content": "hi"}],
            ))
        assert captured["url"] == "http://localhost:11434/v1/chat/completions"

    def test_payload_includes_stream_and_stream_options(self):
        """Payload must carry stream:True, stream_options.include_usage:True."""
        lines = [DONE_LINE]
        captured: dict = {}

        def fake_urlopen(req, timeout=None):
            captured["payload"] = json.loads(req.data.decode("utf-8"))
            return _make_sse_response(*lines)

        with patch(PATCH_TARGET, side_effect=fake_urlopen):
            list(self._prov().chat_completions_stream(
                model="qwen3:8b",
                messages=[{"role": "user", "content": "hi"}],
            ))
        p = captured["payload"]
        assert p["stream"] is True
        assert p["stream_options"] == {"include_usage": True}

    def test_payload_tool_choice_auto_when_tools_present(self):
        """tool_choice='auto' when a non-empty tools list is provided."""
        lines = [DONE_LINE]
        captured: dict = {}

        def fake_urlopen(req, timeout=None):
            captured["payload"] = json.loads(req.data.decode("utf-8"))
            return _make_sse_response(*lines)

        tools = [{"name": "foo", "description": "bar", "parameters": {}}]
        with patch(PATCH_TARGET, side_effect=fake_urlopen):
            list(self._prov().chat_completions_stream(
                model="qwen3:8b",
                messages=[{"role": "user", "content": "hi"}],
                tools=tools,
            ))
        p = captured["payload"]
        assert p["tool_choice"] == "auto"
        assert p["tools"] == tools

    def test_payload_tool_choice_none_when_no_tools(self):
        """tool_choice='none' and tools=[] when tools=None."""
        lines = [DONE_LINE]
        captured: dict = {}

        def fake_urlopen(req, timeout=None):
            captured["payload"] = json.loads(req.data.decode("utf-8"))
            return _make_sse_response(*lines)

        with patch(PATCH_TARGET, side_effect=fake_urlopen):
            list(self._prov().chat_completions_stream(
                model="qwen3:8b",
                messages=[{"role": "user", "content": "hi"}],
                tools=None,
            ))
        p = captured["payload"]
        assert p["tool_choice"] == "none"
        assert p["tools"] == []


# ── OQ-7 _supports_tools probe tests ─────────────────────────────────────────

class TestSupportsTools:
    """Unit tests for OllamaProvider._supports_tools() (OQ-7)."""

    def _prov(self):
        from app.adapters.ai.remote.ollama import OllamaProvider
        return OllamaProvider("http://localhost:11434")

    def _make_show_response(self, template: str):
        """Fake /api/show response with the given chat template."""
        from .conftest import make_response
        return make_response({"template": template})

    def test_returns_true_when_template_contains_tools_keyword(self):
        """Template with 'tools' → True (Jinja `{% if tools %}` pattern)."""
        template = "{% if tools %}{{ tools | tojson }}{% endif %}"
        with patch(PATCH_TARGET, return_value=self._make_show_response(template)):
            assert self._prov()._supports_tools("qwen3:8b") is True

    def test_returns_true_when_template_contains_tool_calls(self):
        """Template with 'tool_calls' → True."""
        template = "{% for tc in tool_calls %}{{ tc.name }}{% endfor %}"
        with patch(PATCH_TARGET, return_value=self._make_show_response(template)):
            assert self._prov()._supports_tools("llama3.1:8b") is True

    def test_returns_true_when_template_contains_function_call(self):
        """Template with 'function_call' → True."""
        template = "{{ function_call.name }}: {{ function_call.arguments }}"
        with patch(PATCH_TARGET, return_value=self._make_show_response(template)):
            assert self._prov()._supports_tools("mistral:7b") is True

    def test_returns_true_when_template_contains_available_tools(self):
        """Template with 'available_tools' → True."""
        template = "Available: {% for t in available_tools %}{{ t.name }} {% endfor %}"
        with patch(PATCH_TARGET, return_value=self._make_show_response(template)):
            assert self._prov()._supports_tools("phi4:14b") is True

    def test_returns_false_when_template_has_no_tool_markers(self):
        """Template without any tool markers → False."""
        template = "{{ system }}\n{% for m in messages %}{{ m.role }}: {{ m.content }}\n{% endfor %}"
        with patch(PATCH_TARGET, return_value=self._make_show_response(template)):
            assert self._prov()._supports_tools("deepseek-r1:7b") is False

    def test_returns_false_when_template_field_absent(self):
        """Missing 'template' key in /api/show response → False (empty string)."""
        from .conftest import make_response
        with patch(PATCH_TARGET, return_value=make_response({"capabilities": ["completion"]})):
            assert self._prov()._supports_tools("some-model") is False

    def test_returns_false_on_connection_error(self):
        """Network failure on /api/show → False (conservative fallback)."""
        import urllib.error
        with patch(PATCH_TARGET, side_effect=urllib.error.URLError("refused")):
            assert self._prov()._supports_tools("qwen3:8b") is False

    def test_returns_false_on_http_error(self):
        """HTTP 404 on /api/show → False (model not found or old Ollama)."""
        import io
        import urllib.error
        err = urllib.error.HTTPError("x", 404, "Not Found", {}, io.BytesIO(b""))
        with patch(PATCH_TARGET, side_effect=err):
            assert self._prov()._supports_tools("unknown") is False


# ── OQ-7 integration: _detect_capabilities fallback path ─────────────────────

class TestDetectCapabilitiesToolsFallback:
    """Verify _detect_capabilities includes 'tools' via template probe in the
    fallback branch (when /api/show returns no 'capabilities' array)."""

    def _prov(self):
        from app.adapters.ai.remote.ollama import OllamaProvider
        return OllamaProvider("http://localhost:11434")

    def test_tools_included_in_fallback_when_template_has_tools(self):
        """When /api/show returns no capabilities, template probe adds 'tools'."""
        from .conftest import make_response
        # First call to /api/show (from _detect_capabilities): no capabilities array
        # Second call (from _supports_tools): template with tools
        responses = iter([
            make_response({"template": "{% if tools %}{% endif %}"}),  # caps missing → fallback
            make_response({"template": "{% if tools %}{% endif %}"}),  # _supports_tools
        ])
        with patch(PATCH_TARGET, side_effect=lambda *a, **kw: next(responses)):
            caps = self._prov()._detect_capabilities("qwen3:8b", [])
        assert "tools" in caps
        assert "text" in caps

    def test_tools_not_included_when_template_lacks_tool_markers(self):
        """Template without tool markers → 'tools' absent from caps."""
        from .conftest import make_response
        plain_template = "{{ system }}\n{% for m in messages %}{% endfor %}"
        responses = iter([
            make_response({"template": plain_template}),  # no capabilities → fallback
            make_response({"template": plain_template}),  # _supports_tools
        ])
        with patch(PATCH_TARGET, side_effect=lambda *a, **kw: next(responses)):
            caps = self._prov()._detect_capabilities("deepseek:7b", [])
        assert "tools" not in caps

    def test_tools_not_duplicated_when_primary_path_already_added_it(self):
        """When /api/show returns capabilities=['completion','tools'], 'tools'
        must appear exactly once (primary path handles it, not template probe)."""
        from .conftest import make_response
        # _detect_capabilities primary path sees capabilities → early return
        with patch(PATCH_TARGET, return_value=make_response(
            {"capabilities": ["completion", "tools"]}
        )):
            caps = self._prov()._detect_capabilities("qwen3:8b", [])
        assert caps.count("tools") == 1
