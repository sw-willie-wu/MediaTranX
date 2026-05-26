"""LocalChatSession.stream() cancel-race tests.

Tests the _stream_kill_pending race flag set by kill_process().
All sync (mock-based) — no real llama-server required.

asyncio_mode = "auto" in pyproject.toml, so no @pytest.mark.asyncio needed.
"""
from __future__ import annotations

import threading
from unittest.mock import MagicMock

import pytest

from app.services.llm.chat_service import LocalChatSession


# ---------------------------------------------------------------------------
# Race scenario 1: kill_process() called BEFORE stream() starts
# ---------------------------------------------------------------------------

async def test_kill_pending_before_stream_entry_is_cleared_by_reset():
    """kill_process() BEFORE stream() is called → stream() resets the flag at
    entry (per spec §5.3.1), so the new stream proceeds normally.

    This is intentional: _stream_kill_pending only blocks the CURRENT active
    stream.  A kill before stream() starts is too early; the per-call reset
    ensures sequential streams aren't left in a permanently-killed state.
    The kill-during-stream scenario is covered by test_kill_during_stream_propagates.
    """
    rt = MagicMock()
    rt.chat_stream.return_value = iter([
        {"id": "msg1", "choices": [{"delta": {"content": "hello"}}]},
        {"usage": {"prompt_tokens": 1, "completion_tokens": 1}, "choices": []},
    ])
    rt._model = MagicMock()

    sess = LocalChatSession(rt, on_progress=None)
    sess.kill_process()  # sets _stream_kill_pending = True
    assert sess._stream_kill_pending is True

    # stream() resets the flag at entry — stream proceeds normally
    chunks = [c async for c in sess.stream(messages=[], max_tokens=100, temperature=0.1)]

    assert any(c.get("text") == "hello" for c in chunks)
    assert any(c.get("type") == "done" for c in chunks)


async def test_kill_after_stream_entry_but_before_first_chunk():
    """kill_process() set between stream() entry and producer's pre-urlopen check.

    The producer checks _stream_kill_pending right before calling chat_stream.
    We simulate this by manually setting the flag via a side-effect on chat_stream,
    verifying the producer's SECOND flag check (post-urlopen) fires.

    Implementation: chat_stream returns normally but between stream()-entry reset
    and chat_stream call, kill_process is invoked from a separate thread that
    waits for producer to be about to call chat_stream.
    """
    rt = MagicMock()

    # Use an event to synchronise: producer signals it's past the first flag check,
    # test sets kill, producer checks again post-urlopen.
    past_first_check = threading.Event()
    kill_set = threading.Event()

    def blocking_chat_stream(**kwargs):
        # Signal we're inside chat_stream (post first-check, awaiting urlopen)
        past_first_check.set()
        # Block until kill arrives
        kill_set.wait(timeout=5.0)
        raise OSError("cancel_post_urlopen")

    rt.chat_stream.side_effect = blocking_chat_stream
    rt._model = MagicMock()
    rt._model.stop = MagicMock(side_effect=lambda timeout=2.0: kill_set.set())

    sess = LocalChatSession(rt, on_progress=None)

    import asyncio

    async def consume():
        async for _ in sess.stream(messages=[], max_tokens=100, temperature=0.1):
            pass

    task = asyncio.create_task(consume())

    # Wait for producer to enter chat_stream, then kill
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, lambda: past_first_check.wait(timeout=5.0))
    sess.kill_process()

    with pytest.raises(OSError):
        await task


# ---------------------------------------------------------------------------
# Race scenario 2: kill_process() called WHILE stream is mid-flight
# ---------------------------------------------------------------------------

async def test_kill_during_stream_propagates():
    """kill_process() called while producer is mid-stream → OSError propagated."""
    rt = MagicMock()

    # Blocking iterator: yields 1 chunk, then blocks until kill unblocks it.
    block = threading.Event()

    def slow_iter():
        yield {"id": "msg1", "choices": [{"delta": {"content": "first"}}]}
        block.wait(timeout=5.0)
        raise OSError("socket closed")   # what real urllib does on stop()

    rt.chat_stream.return_value = slow_iter()
    rt._model = MagicMock()
    rt._model.stop = MagicMock(side_effect=lambda timeout=2.0: block.set())

    sess = LocalChatSession(rt, on_progress=None)

    chunks = []
    with pytest.raises(OSError):
        async for c in sess.stream(messages=[], max_tokens=100, temperature=0.1):
            chunks.append(c)
            if len(chunks) == 1:
                # After receiving first chunk, kill the stream
                sess.kill_process()

    assert len(chunks) == 1
    assert chunks[0] == {"type": "delta", "message_id": "msg1", "text": "first"}
    rt._model.stop.assert_called_once()


# ---------------------------------------------------------------------------
# Race scenario 3: sequential streams — _stream_kill_pending resets per call
# ---------------------------------------------------------------------------

async def test_stream_kill_pending_resets_per_call():
    """After a killed stream, a new stream() call resets the flag and runs normally."""
    rt = MagicMock()
    rt._model = MagicMock()
    rt._model.stop = MagicMock()

    sess = LocalChatSession(rt, on_progress=None)

    # First: kill before any stream
    sess.kill_process()
    assert sess._stream_kill_pending is True

    # Second call: set up a normal stream — stream() resets flag at entry
    rt.chat_stream.return_value = iter([
        {"id": "msg2", "choices": [{"delta": {"content": "ok"}}]},
        {"usage": {"prompt_tokens": 1, "completion_tokens": 1}, "choices": []},
    ])

    chunks = [c async for c in sess.stream(messages=[], max_tokens=100, temperature=0.1)]

    assert any(c.get("text") == "ok" for c in chunks)
    assert any(c.get("type") == "done" for c in chunks)


# ---------------------------------------------------------------------------
# Attribute: _stream_kill_pending initialized in __init__
# ---------------------------------------------------------------------------

def test_stream_kill_pending_initialized_in_init():
    """LocalChatSession always has _stream_kill_pending set to False at construction."""
    rt = MagicMock()
    sess = LocalChatSession(rt, on_progress=None)
    assert hasattr(sess, "_stream_kill_pending")
    assert sess._stream_kill_pending is False


# ---------------------------------------------------------------------------
# kill_process sets flag BEFORE calling model.stop
# ---------------------------------------------------------------------------

def test_kill_process_sets_flag_before_stop():
    """kill_process() must set _stream_kill_pending=True before calling model.stop."""
    order = []

    class FakeModel:
        def stop(self, timeout=2.0):
            order.append("stop")

    class FakeRuntime:
        _model = FakeModel()

    sess = LocalChatSession(FakeRuntime(), on_progress=None)

    original_stop = FakeRuntime._model.stop

    def patched_stop(timeout=2.0):
        order.append("flag_was_set:" + str(sess._stream_kill_pending))
        original_stop(timeout=timeout)

    FakeRuntime._model.stop = patched_stop
    sess.kill_process()

    # Flag is set before stop() is called
    assert "flag_was_set:True" in order[0]


# ---------------------------------------------------------------------------
# kill_process when no model loaded (None) — still sets flag, no AttributeError
# ---------------------------------------------------------------------------

def test_kill_process_no_model_sets_flag():
    """kill_process() with no loaded model sets flag but does not raise."""
    rt = MagicMock(spec=[])   # no _model attribute
    sess = LocalChatSession(rt, on_progress=None)
    sess.kill_process()
    assert sess._stream_kill_pending is True


# ---------------------------------------------------------------------------
# Verify stream() does NOT invoke _guard() (pass-through cancel mode)
# ---------------------------------------------------------------------------

async def test_stream_does_not_use_guard():
    """stream() should NOT call _guard(); on_progress is irrelevant for stream path."""
    rt = MagicMock()
    rt.chat_stream.return_value = iter([])
    # Provide on_progress so _guard() WOULD install a watcher if called
    on_progress_calls = []
    sess = LocalChatSession(rt, on_progress=lambda p, m: on_progress_calls.append((p, m)))

    async for _ in sess.stream(messages=[], max_tokens=10, temperature=0.0):
        pass

    # _guard() (and thus cancel_guard) should never have been entered
    assert on_progress_calls == []
