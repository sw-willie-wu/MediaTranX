"""Tests for OpenAIProvider.chat_completions_stream() generator.

Covers:
- Happy path: text deltas + final usage chunk
- Tool-call deltas across multiple chunks
- 4xx HTTP error raises immediately
- abort_hook invoked after urlopen
- Malformed JSON lines are skipped with a warning
- [DONE] terminator stops the generator
- tools/tool_choice wiring in request payload
- stream_options.include_usage present in payload
- Responses-API path raises NotImplementedError (chat_responses_stream stub)
"""
import json
import logging
from unittest.mock import MagicMock, patch

import pytest


# ── Helper ──────────────────────────────────────────────────────────────────

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


def _tool_line(index: int, tc_id: str, name: str, args: str, chunk_id: str = "c1") -> bytes:
    obj = {
        "id": chunk_id,
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


# ── Tests ────────────────────────────────────────────────────────────────────

class TestChatCompletionsStream:

    def _prov(self):
        from app.adapters.ai.remote.openai import OpenAIProvider
        return OpenAIProvider("https://api.openai.com", "sk-test")

    def test_happy_path_text_chunks(self):
        """Yields raw chunk dicts for each text delta; [DONE] stops the generator."""
        lines = [
            _delta_line("Hello", "msg1"),
            _delta_line(" world", "msg1"),
            DONE_LINE,
        ]
        with patch(
            "app.adapters.ai.remote._http.urlopen",
            return_value=_make_sse_response(*lines),
        ):
            chunks = list(self._prov().chat_completions_stream(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": "hi"}],
            ))
        assert len(chunks) == 2
        assert chunks[0]["choices"][0]["delta"]["content"] == "Hello"
        assert chunks[1]["choices"][0]["delta"]["content"] == " world"

    def test_usage_chunk_yielded(self):
        """Final usage chunk is yielded so caller can capture it."""
        lines = [_delta_line("x"), _usage_line(prompt=20, completion=3), DONE_LINE]
        with patch(
            "app.adapters.ai.remote._http.urlopen",
            return_value=_make_sse_response(*lines),
        ):
            chunks = list(self._prov().chat_completions_stream(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": "hi"}],
            ))
        usage_chunks = [c for c in chunks if "usage" in c]
        assert len(usage_chunks) == 1
        assert usage_chunks[0]["usage"]["prompt_tokens"] == 20

    def test_tool_call_deltas_yielded(self):
        """Tool-call deltas are yielded as raw chunks."""
        lines = [
            _tool_line(0, "tc1", "navigate_to", '{"route":"/video"}'),
            DONE_LINE,
        ]
        with patch(
            "app.adapters.ai.remote._http.urlopen",
            return_value=_make_sse_response(*lines),
        ):
            chunks = list(self._prov().chat_completions_stream(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": "go to video"}],
                tools=[{
                    "name": "navigate_to",
                    "description": "nav",
                    "parameters": {"type": "object", "properties": {}},
                }],
            ))
        assert len(chunks) == 1
        tc = chunks[0]["choices"][0]["delta"]["tool_calls"][0]
        assert tc["function"]["name"] == "navigate_to"
        assert '"/video"' in tc["function"]["arguments"]

    def test_4xx_http_error_raises_immediately(self):
        """HTTPError from urlopen → RuntimeError before any chunks are yielded."""
        import urllib.error
        from app.handler.exceptions import RemoteApiError

        def fake_urlopen(req, timeout=None):
            raise urllib.error.HTTPError(
                req.full_url, 401,
                "Unauthorized", {}, None,
            )

        # HTTPError.read() is called to get the body
        with patch(
            "app.adapters.ai.remote._http.urlopen",
            side_effect=fake_urlopen,
        ):
            with pytest.raises(RemoteApiError) as exc_info:
                list(self._prov().chat_completions_stream(
                    model="gpt-4o-mini",
                    messages=[{"role": "user", "content": "hi"}],
                ))
        assert exc_info.value.code == "auth_failed"

    def test_abort_hook_called_after_urlopen(self):
        """abort_hook receives the response object immediately after urlopen returns."""
        lines = [DONE_LINE]
        resp = _make_sse_response(*lines)
        hook_received = []

        with patch(
            "app.adapters.ai.remote._http.urlopen",
            return_value=resp,
        ):
            list(self._prov().chat_completions_stream(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": "hi"}],
                abort_hook=lambda r: hook_received.append(r),
            ))
        assert len(hook_received) == 1
        assert hook_received[0] is resp

    def test_malformed_json_skipped_with_warning(self, caplog):
        """Non-parseable JSON lines emit a warning and are skipped."""
        bad_line = b"data: {this is not json}\n"
        lines = [
            bad_line,
            _delta_line("ok"),
            DONE_LINE,
        ]
        with caplog.at_level(logging.WARNING, logger="app.adapters.ai.remote.openai"):
            with patch(
                "app.adapters.ai.remote._http.urlopen",
                return_value=_make_sse_response(*lines),
            ):
                chunks = list(self._prov().chat_completions_stream(
                    model="gpt-4o-mini",
                    messages=[{"role": "user", "content": "hi"}],
                ))
        # Only valid chunk yielded
        assert len(chunks) == 1
        assert chunks[0]["choices"][0]["delta"]["content"] == "ok"
        assert any("malformed" in r.message.lower() for r in caplog.records)

    def test_done_terminator_stops_iteration(self):
        """[DONE] before end of HTTP stream still stops the generator cleanly."""
        lines = [
            _delta_line("a"),
            DONE_LINE,
            _delta_line("should_not_appear"),  # after [DONE] — must be ignored
        ]
        with patch(
            "app.adapters.ai.remote._http.urlopen",
            return_value=_make_sse_response(*lines),
        ):
            chunks = list(self._prov().chat_completions_stream(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": "hi"}],
            ))
        assert len(chunks) == 1
        assert chunks[0]["choices"][0]["delta"]["content"] == "a"

    def test_payload_includes_tools_and_stream_options(self):
        """Request payload carries tools (wrapped to OpenAI strict shape),
        tool_choice, stream, stream_options."""
        lines = [DONE_LINE]
        captured: dict = {}

        def fake_urlopen(req, timeout=None):
            captured["payload"] = json.loads(req.data.decode("utf-8"))
            return _make_sse_response(*lines)

        tools = [{
            "name": "foo",
            "description": "bar",
            "parameters": {"type": "object", "properties": {}},
        }]
        with patch(
            "app.adapters.ai.remote._http.urlopen",
            side_effect=fake_urlopen,
        ):
            list(self._prov().chat_completions_stream(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": "hi"}],
                tools=tools,
            ))
        p = captured["payload"]
        assert p["stream"] is True
        assert p["stream_options"] == {"include_usage": True}
        assert p["tool_choice"] == "auto"
        # NEW: tools are wrapped to OpenAI strict shape, not passed through flat
        assert len(p["tools"]) == 1
        entry = p["tools"][0]
        assert entry["type"] == "function"
        assert entry["function"]["name"] == "foo"
        assert entry["function"]["description"] == "bar"
        assert entry["function"]["strict"] is True
        # parameters were strict-ified (zero-arg → additionalProperties:false)
        params = entry["function"]["parameters"]
        assert params["additionalProperties"] is False
        assert params["required"] == []

    def test_payload_tool_choice_none_when_no_tools(self):
        """tool_choice='none' when tools=[] or tools=None."""
        lines = [DONE_LINE]
        captured: dict = {}

        def fake_urlopen(req, timeout=None):
            captured["payload"] = json.loads(req.data.decode("utf-8"))
            return _make_sse_response(*lines)

        with patch(
            "app.adapters.ai.remote._http.urlopen",
            side_effect=fake_urlopen,
        ):
            list(self._prov().chat_completions_stream(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": "hi"}],
                tools=None,
            ))
        assert captured["payload"]["tool_choice"] == "none"
        assert captured["payload"]["tools"] == []

    def test_resp_closed_after_iteration(self):
        """Response.close() is always called in the finally block."""
        lines = [_delta_line("x"), DONE_LINE]
        resp = _make_sse_response(*lines)
        with patch(
            "app.adapters.ai.remote._http.urlopen",
            return_value=resp,
        ):
            list(self._prov().chat_completions_stream(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": "hi"}],
            ))
        resp.close.assert_called_once()


class TestChatResponsesStreamStub:
    """chat_responses_stream raises NotImplementedError in Phase 1."""

    def test_raises_not_implemented(self):
        from app.adapters.ai.remote.openai import OpenAIProvider

        prov = OpenAIProvider("https://api.openai.com", "sk-test")
        with pytest.raises(NotImplementedError, match="Responses streaming"):
            list(prov.chat_responses_stream(
                model="o4-mini",
                messages=[{"role": "user", "content": "x"}],
            ))


# ── RemoteChatSession.stream() integration ──────────────────────────────────

class TestRemoteChatSessionStream:
    """Unit tests for RemoteChatSession.stream() — uses a fake provider."""

    def _fake_provider(self, chunks: list[dict]):
        """Build a MagicMock provider whose chat_completions_stream returns chunks."""
        prov = MagicMock()
        prov.chat_completions_stream = MagicMock(return_value=iter(chunks))
        return prov

    async def test_stream_yields_parsed_events(self):
        """Parsed delta + done events reach the caller."""
        raw_chunks = [
            {"id": "c1", "choices": [{"delta": {"content": "hi"}}]},
            {"usage": {"prompt_tokens": 5, "completion_tokens": 2}},
        ]
        from app.services.llm.remote_chat import RemoteChatSession

        prov = self._fake_provider(raw_chunks)
        sess = RemoteChatSession(prov, "gpt-4o-mini")
        events = []
        async for ev in sess.stream(
            messages=[{"role": "user", "content": "hi"}],
            max_tokens=100, temperature=0.1,
        ):
            events.append(ev)

        delta_events = [e for e in events if e["type"] == "delta"]
        done_events = [e for e in events if e["type"] == "done"]
        assert len(delta_events) == 1
        assert delta_events[0]["text"] == "hi"
        assert len(done_events) == 1
        assert done_events[0]["usage"]["prompt_tokens"] == 5

    async def test_stream_raises_not_implemented_when_provider_lacks_method(self):
        """Providers without chat_completions_stream raise NotImplementedError."""
        from app.services.llm.remote_chat import RemoteChatSession

        prov = MagicMock(spec=[])  # no chat_completions_stream attribute
        sess = RemoteChatSession(prov, "some-model")
        with pytest.raises(NotImplementedError, match="chat_completions_stream"):
            async for _ in sess.stream(
                messages=[{"role": "user", "content": "hi"}],
                max_tokens=100, temperature=0.1,
            ):
                pass

    async def test_stream_propagates_provider_exception(self):
        """Exceptions from the provider iterator propagate to the caller."""
        from app.services.llm.remote_chat import RemoteChatSession

        def _exploding():
            yield {"id": "c1", "choices": [{"delta": {"content": "x"}}]}
            raise RuntimeError("upstream boom")

        prov = MagicMock()
        prov.chat_completions_stream = MagicMock(return_value=_exploding())
        sess = RemoteChatSession(prov, "gpt-4o-mini")
        with pytest.raises(RuntimeError, match="upstream boom"):
            async for _ in sess.stream(
                messages=[{"role": "user", "content": "hi"}],
                max_tokens=100, temperature=0.1,
            ):
                pass

    async def test_stream_kill_process_sets_flags(self):
        """kill_process() sets both _kill_pending and _stream_kill_pending."""
        from app.services.llm.remote_chat import RemoteChatSession

        prov = MagicMock()
        sess = RemoteChatSession(prov, "gpt-4o-mini")
        sess.kill_process()
        assert sess._kill_pending is True
        assert sess._stream_kill_pending is True
