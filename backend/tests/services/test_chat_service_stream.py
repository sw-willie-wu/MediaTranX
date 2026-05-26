"""LocalChatSession.stream() happy-path tests.

Tests producer-thread + asyncio.Queue bridge and _parse_openai_compat_chunk
helper.  All sync (mock-based) — no real llama-server required.

asyncio_mode = "auto" in pyproject.toml, so no @pytest.mark.asyncio needed.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.services.llm.chat_service import LocalChatSession, _parse_openai_compat_chunk


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_session(**kwargs) -> LocalChatSession:
    """Return a LocalChatSession with a MagicMock runtime."""
    rt = MagicMock()
    return LocalChatSession(rt, on_progress=None, **kwargs)


def _runtime_with_stream(chunks) -> MagicMock:
    rt = MagicMock()
    rt.chat_stream.return_value = iter(chunks)
    return rt


# ---------------------------------------------------------------------------
# stream() — happy path
# ---------------------------------------------------------------------------

async def test_stream_yields_delta_and_done_with_usage():
    """Producer yields 3 text chunks + 1 usage chunk → stream yields 3 deltas + done."""
    rt = _runtime_with_stream([
        {"id": "msg1", "choices": [{"delta": {"content": "hello"}}]},
        {"id": "msg1", "choices": [{"delta": {"content": " world"}}]},
        {"id": "msg1", "choices": [{"delta": {"content": "!"}}]},
        {"usage": {"prompt_tokens": 10, "completion_tokens": 3}, "choices": []},
    ])
    sess = LocalChatSession(rt, on_progress=None)

    chunks = []
    async for c in sess.stream(messages=[{"role": "user", "content": "hi"}],
                               max_tokens=100, temperature=0.1):
        chunks.append(c)

    assert len(chunks) == 4   # 3 deltas + 1 done
    assert chunks[0] == {"type": "delta", "message_id": "msg1", "text": "hello"}
    assert chunks[1] == {"type": "delta", "message_id": "msg1", "text": " world"}
    assert chunks[2] == {"type": "delta", "message_id": "msg1", "text": "!"}
    assert chunks[3] == {
        "type": "done",
        "usage": {"prompt_tokens": 10, "completion_tokens": 3},
    }


async def test_stream_done_usage_none_when_no_usage_chunk():
    """When the stream has no usage chunk, done.usage is None."""
    rt = _runtime_with_stream([
        {"id": "msg1", "choices": [{"delta": {"content": "hi"}}]},
    ])
    sess = LocalChatSession(rt, on_progress=None)

    chunks = [c async for c in sess.stream(messages=[], max_tokens=50, temperature=0.0)]

    assert chunks[-1]["type"] == "done"
    assert chunks[-1]["usage"] is None


async def test_stream_yields_tool_call_deltas():
    """Producer yields tool_call args in 2 fragments → stream yields 2 tool_call events."""
    rt = _runtime_with_stream([
        {"id": "msg1", "choices": [{"delta": {"tool_calls": [
            {"index": 0, "id": "tc1", "function": {"name": "set_field", "arguments": '{"fie'}}
        ]}}]},
        {"id": "msg1", "choices": [{"delta": {"tool_calls": [
            {"index": 0, "function": {"arguments": 'ld":"x"}'}}
        ]}}]},
        {"id": "msg1", "choices": []},   # finish chunk (empty delta → 0 events)
        {"usage": {"prompt_tokens": 5, "completion_tokens": 7}, "choices": []},
    ])
    sess = LocalChatSession(rt, on_progress=None)

    chunks = [c async for c in sess.stream(messages=[], max_tokens=100, temperature=0.1)]

    # 2 tool_call deltas + 1 done
    tc_events = [c for c in chunks if c.get("type") == "tool_call"]
    assert len(tc_events) == 2
    assert tc_events[0] == {
        "type": "tool_call",
        "id": "tc1",
        "name": "set_field",
        "parent_message_id": "msg1",
        "args_delta": '{"fie',
    }
    assert tc_events[1] == {
        "type": "tool_call",
        "id": "",           # id absent on 2nd chunk → defaults to ""
        "name": "",         # name absent on 2nd chunk → defaults to ""
        "parent_message_id": "msg1",
        "args_delta": 'ld":"x"}',
    }
    assert any(c.get("type") == "done" for c in chunks)


async def test_stream_propagates_producer_exception():
    """If chat_stream raises immediately, stream() propagates the exception."""
    rt = MagicMock()
    rt.chat_stream.side_effect = RuntimeError("boom")
    sess = LocalChatSession(rt, on_progress=None)

    with pytest.raises(RuntimeError, match="boom"):
        async for _ in sess.stream(messages=[], max_tokens=100, temperature=0.1):
            pass


async def test_stream_propagates_mid_iteration_exception():
    """If chat_stream raises mid-iteration, stream() propagates the exception."""
    def bad_iter():
        yield {"id": "m1", "choices": [{"delta": {"content": "first"}}]}
        raise ValueError("mid-stream failure")

    rt = MagicMock()
    rt.chat_stream.return_value = bad_iter()
    sess = LocalChatSession(rt, on_progress=None)

    chunks = []
    with pytest.raises(ValueError, match="mid-stream failure"):
        async for c in sess.stream(messages=[], max_tokens=100, temperature=0.1):
            chunks.append(c)

    assert len(chunks) == 1
    assert chunks[0]["text"] == "first"


async def test_stream_empty_input_just_done():
    """An empty stream (no content) yields just the done event with no usage."""
    rt = _runtime_with_stream([])
    sess = LocalChatSession(rt, on_progress=None)

    chunks = [c async for c in sess.stream(messages=[], max_tokens=10, temperature=0.0)]

    assert len(chunks) == 1
    assert chunks[0] == {"type": "done", "usage": None}


async def test_stream_passes_tools_to_runtime():
    """stream() forwards the tools argument to chat_stream."""
    rt = _runtime_with_stream([])
    sess = LocalChatSession(rt, on_progress=None)

    tools = [{"type": "function", "function": {"name": "navigate_to"}}]
    async for _ in sess.stream(messages=[], tools=tools, max_tokens=50, temperature=0.0):
        pass

    call_kwargs = rt.chat_stream.call_args.kwargs
    assert call_kwargs["tools"] == tools
    assert call_kwargs["max_tokens"] == 50
    assert call_kwargs["temperature"] == 0.0


async def test_stream_mixed_delta_and_tool_call():
    """A chunk with both text and tool_call in the same delta produces both events."""
    rt = _runtime_with_stream([
        {"id": "m1", "choices": [{"delta": {
            "content": "thinking...",
            "tool_calls": [{"index": 0, "id": "tc2", "function": {"name": "click_execute", "arguments": "{}"}}],
        }}]},
    ])
    sess = LocalChatSession(rt, on_progress=None)

    chunks = [c async for c in sess.stream(messages=[], max_tokens=50, temperature=0.0)]
    types = [c["type"] for c in chunks]

    assert "delta" in types
    assert "tool_call" in types
    assert "done" in types


# ---------------------------------------------------------------------------
# _parse_openai_compat_chunk helper — unit tests
# ---------------------------------------------------------------------------

def test_parse_empty_choices_returns_empty():
    """Usage-only chunks have empty choices → return []."""
    result = _parse_openai_compat_chunk({"usage": {"prompt_tokens": 5, "completion_tokens": 3}, "choices": []})
    assert result == []


def test_parse_no_choices_key_returns_empty():
    """Chunk without 'choices' key at all → return []."""
    assert _parse_openai_compat_chunk({"id": "x"}) == []


def test_parse_text_delta():
    """Content delta produces a single 'delta' event."""
    result = _parse_openai_compat_chunk({
        "id": "msg42",
        "choices": [{"delta": {"content": "hello"}}],
    })
    assert result == [{"type": "delta", "message_id": "msg42", "text": "hello"}]


def test_parse_empty_content_skipped():
    """Empty string content (falsy) → no delta event emitted."""
    result = _parse_openai_compat_chunk({
        "id": "msg1",
        "choices": [{"delta": {"content": ""}}],
    })
    assert result == []


def test_parse_finish_reason_chunk_returns_empty():
    """Finish-reason chunks have empty delta → 0 events."""
    result = _parse_openai_compat_chunk({
        "id": "msg1",
        "choices": [{"delta": {}, "finish_reason": "stop"}],
    })
    assert result == []


def test_parse_tool_call_first_chunk():
    """First tool_call chunk carries id and name."""
    result = _parse_openai_compat_chunk({
        "id": "msg2",
        "choices": [{"delta": {"tool_calls": [
            {"index": 0, "id": "tc1", "function": {"name": "navigate_to", "arguments": '{"url"'}}
        ]}}],
    })
    assert len(result) == 1
    assert result[0] == {
        "type": "tool_call",
        "id": "tc1",
        "name": "navigate_to",
        "parent_message_id": "msg2",
        "args_delta": '{"url"',
    }


def test_parse_tool_call_continuation_chunk():
    """Continuation chunk has no id or name — defaults to empty string."""
    result = _parse_openai_compat_chunk({
        "id": "msg2",
        "choices": [{"delta": {"tool_calls": [
            {"index": 0, "function": {"arguments": ':"https://x.com"}'}}
        ]}}],
    })
    assert len(result) == 1
    assert result[0]["id"] == ""
    assert result[0]["name"] == ""
    assert result[0]["args_delta"] == ':"https://x.com"}'


def test_parse_multiple_tool_calls_in_single_chunk():
    """Multiple tool_calls in one chunk → multiple events."""
    result = _parse_openai_compat_chunk({
        "id": "msg3",
        "choices": [{"delta": {"tool_calls": [
            {"index": 0, "id": "tc1", "function": {"name": "set_field", "arguments": "{}"}},
            {"index": 1, "id": "tc2", "function": {"name": "click_execute", "arguments": "{}"}},
        ]}}],
    })
    assert len(result) == 2
    assert result[0]["name"] == "set_field"
    assert result[1]["name"] == "click_execute"


def test_parse_id_defaults_to_empty_string_when_absent():
    """chunk['id'] absent → message_id defaults to ''."""
    result = _parse_openai_compat_chunk({
        "choices": [{"delta": {"content": "x"}}],
    })
    assert result[0]["message_id"] == ""
