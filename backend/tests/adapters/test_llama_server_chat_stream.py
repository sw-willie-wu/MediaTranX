"""Unit tests for LlamaServer.chat_stream() — mock-based SSE parsing.

Tests feed predetermined SSE byte lines through a mocked urllib.request.urlopen
and verify correct generator behaviour without a real llama-server process.

Patch target: ``urllib.request.urlopen`` directly (not via module attribute),
because LlamaServer.chat_stream() imports urllib lazily inside the method body.
"""
from __future__ import annotations

import json
import logging
from unittest.mock import MagicMock, patch

import pytest

from app.adapters.binary.llama_server import LlamaServer

# Patch target: chat_stream() does `import urllib.request` inside the method,
# so the canonical mock target is the stdlib module directly.
_URLOPEN = "urllib.request.urlopen"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_sse_response(*lines: bytes) -> MagicMock:
    """Build a mock HTTP response object whose iteration yields given byte lines."""
    resp = MagicMock(name="HTTPResponse")
    resp.__iter__ = lambda self: iter(lines)
    resp.__enter__ = MagicMock(return_value=resp)
    resp.__exit__ = MagicMock(return_value=False)
    resp.close = MagicMock()
    return resp


def _server_at_port(port: int = 18080) -> LlamaServer:
    """Return a LlamaServer with _port pre-set (no subprocess)."""
    server = LlamaServer()
    server._port = port
    return server


def _sse(payload: str) -> bytes:
    return f"data: {payload}\n".encode("utf-8")


def _done() -> bytes:
    return b"data: [DONE]\n"


def _chunk(content: str | None = None, tool_calls: list | None = None, usage: dict | None = None) -> dict:
    """Build a minimal OpenAI-compat SSE chunk dict."""
    delta: dict = {}
    if content is not None:
        delta["content"] = content
    if tool_calls is not None:
        delta["tool_calls"] = tool_calls
    chunk: dict = {}
    if delta:
        chunk["choices"] = [{"delta": delta}]
    if usage is not None:
        chunk["usage"] = usage
    return chunk


# ---------------------------------------------------------------------------
# Case 1: plain text response — N delta chunks + 1 usage chunk + [DONE]
# ---------------------------------------------------------------------------

def test_plain_text_response_yields_delta_and_usage_chunks():
    server = _server_at_port()
    delta1 = _chunk(content="Hello")
    delta2 = _chunk(content=" world")
    usage_chunk = {"choices": [{"delta": {}}], "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}}

    lines = [
        _sse(json.dumps(delta1)),
        _sse(json.dumps(delta2)),
        _sse(json.dumps(usage_chunk)),
        _done(),
    ]
    resp = _make_sse_response(*lines)

    with patch(_URLOPEN, return_value=resp):
        chunks = list(server.chat_stream(messages=[{"role": "user", "content": "hi"}]))

    assert len(chunks) == 3
    assert chunks[0] == delta1
    assert chunks[1] == delta2
    assert chunks[2]["usage"]["total_tokens"] == 15


# ---------------------------------------------------------------------------
# Case 2: tool call response — deltas with tool_calls field yielded raw
# ---------------------------------------------------------------------------

def test_tool_call_response_yields_tool_call_chunks_raw():
    server = _server_at_port()
    tc_chunk1 = _chunk(tool_calls=[{"index": 0, "id": "call_1", "function": {"name": "set_field", "arguments": ""}}])
    tc_chunk2 = _chunk(tool_calls=[{"index": 0, "function": {"arguments": '{"field":'}}])
    tc_chunk3 = _chunk(tool_calls=[{"index": 0, "function": {"arguments": '"model","value":"x4plus"}'}}])
    usage_chunk = {"usage": {"prompt_tokens": 20, "completion_tokens": 10, "total_tokens": 30}}

    lines = [
        _sse(json.dumps(tc_chunk1)),
        _sse(json.dumps(tc_chunk2)),
        _sse(json.dumps(tc_chunk3)),
        _sse(json.dumps(usage_chunk)),
        _done(),
    ]
    resp = _make_sse_response(*lines)

    with patch(_URLOPEN, return_value=resp):
        chunks = list(server.chat_stream(
            messages=[{"role": "user", "content": "call set_field"}],
            tools=[{"type": "function", "function": {"name": "set_field", "parameters": {}}}],
        ))

    assert len(chunks) == 4
    assert chunks[0]["choices"][0]["delta"]["tool_calls"][0]["id"] == "call_1"
    assert chunks[1]["choices"][0]["delta"]["tool_calls"][0]["function"]["arguments"] == '{"field":'
    assert chunks[2]["choices"][0]["delta"]["tool_calls"][0]["function"]["arguments"] == '"model","value":"x4plus"}'
    assert chunks[3]["usage"]["total_tokens"] == 30


# ---------------------------------------------------------------------------
# Case 3: usage chunk is last before [DONE]
# ---------------------------------------------------------------------------

def test_usage_chunk_is_last_in_sequence():
    server = _server_at_port()
    delta = _chunk(content="answer")
    usage_chunk = {"usage": {"prompt_tokens": 5, "completion_tokens": 1, "total_tokens": 6}}

    lines = [
        _sse(json.dumps(delta)),
        _sse(json.dumps(usage_chunk)),
        _done(),
    ]
    resp = _make_sse_response(*lines)

    with patch(_URLOPEN, return_value=resp):
        chunks = list(server.chat_stream(messages=[{"role": "user", "content": "x"}]))

    assert "usage" in chunks[-1]
    assert chunks[-1]["usage"]["prompt_tokens"] == 5


# ---------------------------------------------------------------------------
# Case 4: malformed JSON mid-stream — warning logged, generator continues
# ---------------------------------------------------------------------------

def test_malformed_json_mid_stream_skipped_with_warning(caplog):
    server = _server_at_port()
    good_chunk = _chunk(content="ok")
    lines = [
        _sse(json.dumps(good_chunk)),
        b"data: {not valid json}\n",
        _sse(json.dumps(_chunk(content=" done"))),
        _done(),
    ]
    resp = _make_sse_response(*lines)

    with caplog.at_level(logging.WARNING, logger="app.adapters.binary.llama_server"):
        with patch(_URLOPEN, return_value=resp):
            chunks = list(server.chat_stream(messages=[{"role": "user", "content": "x"}]))

    # Generator continues past the bad line — 2 valid chunks yielded
    assert len(chunks) == 2
    assert chunks[0]["choices"][0]["delta"]["content"] == "ok"
    assert chunks[1]["choices"][0]["delta"]["content"] == " done"
    # Warning was logged
    assert any("malformed JSON" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# Case 5: HTTP 4xx / 5xx → raises RuntimeError, nothing yielded
# ---------------------------------------------------------------------------

def test_http_4xx_raises_runtime_error():
    import urllib.error

    server = _server_at_port()

    http_err = urllib.error.HTTPError(
        url="http://127.0.0.1:18080/v1/chat/completions",
        code=400,
        msg="Bad Request",
        hdrs=MagicMock(),  # type: ignore[arg-type]
        fp=None,
    )
    http_err.read = lambda: b'{"error":"bad_request"}'

    with patch(_URLOPEN, side_effect=http_err):
        with pytest.raises(RuntimeError, match="400"):
            list(server.chat_stream(messages=[{"role": "user", "content": "x"}]))


def test_http_5xx_raises_runtime_error():
    import urllib.error

    server = _server_at_port()

    http_err = urllib.error.HTTPError(
        url="http://127.0.0.1:18080/v1/chat/completions",
        code=500,
        msg="Internal Server Error",
        hdrs=MagicMock(),  # type: ignore[arg-type]
        fp=None,
    )
    http_err.read = lambda: b'{"error":"internal"}'

    with patch(_URLOPEN, side_effect=http_err):
        with pytest.raises(RuntimeError, match="500"):
            list(server.chat_stream(messages=[{"role": "user", "content": "x"}]))


# ---------------------------------------------------------------------------
# Case 6: connection abort mid-stream — exception propagates from generator
# ---------------------------------------------------------------------------

def test_connection_abort_mid_stream_propagates():
    server = _server_at_port()

    def _abort_iter():
        yield _sse(json.dumps(_chunk(content="first")))
        raise ConnectionResetError("connection reset by peer")

    resp = MagicMock(name="HTTPResponse")
    resp.__iter__ = lambda self: _abort_iter()
    resp.close = MagicMock()

    with patch(_URLOPEN, return_value=resp):
        gen = server.chat_stream(messages=[{"role": "user", "content": "x"}])
        first = next(gen)
        assert first["choices"][0]["delta"]["content"] == "first"
        with pytest.raises(ConnectionResetError):
            next(gen)


# ---------------------------------------------------------------------------
# Guard: not-started server raises before any HTTP call
# ---------------------------------------------------------------------------

def test_chat_stream_raises_when_not_started():
    server = LlamaServer()  # _port is None
    with pytest.raises(RuntimeError, match="not started"):
        list(server.chat_stream(messages=[{"role": "user", "content": "x"}]))


# ---------------------------------------------------------------------------
# Payload shape checks
# ---------------------------------------------------------------------------

def test_chat_stream_sends_correct_payload():
    server = _server_at_port()
    resp = _make_sse_response(_done())
    captured: dict = {}

    def fake_urlopen(req, timeout=None):
        captured["payload"] = json.loads(req.data.decode("utf-8"))
        captured["url"] = req.full_url
        return resp

    tools = [{"type": "function", "function": {"name": "foo"}}]
    with patch(_URLOPEN, side_effect=fake_urlopen):
        list(server.chat_stream(
            messages=[{"role": "user", "content": "x"}],
            tools=tools,
            max_tokens=512,
            temperature=0.7,
        ))

    p = captured["payload"]
    assert p["stream"] is True
    assert p["stream_options"] == {"include_usage": True}
    assert p["tool_choice"] == "auto"
    assert p["max_tokens"] == 512
    assert p["temperature"] == 0.7
    assert "127.0.0.1:18080/v1/chat/completions" in captured["url"]


def test_chat_stream_tool_choice_none_when_no_tools():
    """When tools list is empty/None, tool_choice must be 'none'."""
    server = _server_at_port()
    resp = _make_sse_response(_done())
    captured: dict = {}

    def fake_urlopen(req, timeout=None):
        captured["payload"] = json.loads(req.data.decode("utf-8"))
        return resp

    with patch(_URLOPEN, side_effect=fake_urlopen):
        list(server.chat_stream(messages=[{"role": "user", "content": "x"}]))

    assert captured["payload"]["tool_choice"] == "none"
    assert captured["payload"]["tools"] == []


def test_chat_stream_empty_lines_skipped():
    """Blank / whitespace-only SSE lines must not crash the generator."""
    server = _server_at_port()
    good = _chunk(content="hi")
    lines = [
        b"\n",
        b"  \n",
        _sse(json.dumps(good)),
        b"\n",
        _done(),
    ]
    resp = _make_sse_response(*lines)

    with patch(_URLOPEN, return_value=resp):
        chunks = list(server.chat_stream(messages=[{"role": "user", "content": "x"}]))

    assert len(chunks) == 1
    assert chunks[0]["choices"][0]["delta"]["content"] == "hi"


def test_chat_stream_resp_close_called_after_exhaustion():
    """Response is always closed, even on normal exit."""
    server = _server_at_port()
    resp = _make_sse_response(_done())

    with patch(_URLOPEN, return_value=resp):
        list(server.chat_stream(messages=[{"role": "user", "content": "x"}]))

    resp.close.assert_called_once()


def test_chat_stream_resp_close_called_on_exception():
    """Response is closed even when an exception propagates."""
    server = _server_at_port()

    def _error_iter():
        raise OSError("socket closed")
        yield  # make it a generator

    resp = MagicMock(name="HTTPResponse")
    resp.__iter__ = lambda self: _error_iter()
    resp.close = MagicMock()

    with patch(_URLOPEN, return_value=resp):
        with pytest.raises(OSError):
            list(server.chat_stream(messages=[{"role": "user", "content": "x"}]))

    resp.close.assert_called_once()
