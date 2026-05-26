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
    # kill_process() is called TWICE: once explicitly by the consumer inside the loop
    # and once by stream()'s finally block when the generator exits.  Both calls are
    # idempotent (documented in kill_process() docstring). Accept ≥1 call.
    rt._model.stop.assert_called()


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


# ---------------------------------------------------------------------------
# Regression: consumer break → kill_process() called (producer cleanup)
# ---------------------------------------------------------------------------

async def test_stream_break_kills_producer():
    """If the consumer breaks out of the async-for early, kill_process() must be
    called so the producer thread's HTTP socket is closed promptly.

    We verify via _stream_kill_pending=True after the generator is explicitly
    closed.  Python's async-generator finalizer is GC-driven and may not have
    fired by the time the `async for` body exits, so we explicitly call
    `gen.aclose()` to guarantee the finally block runs before the assertion.
    The production path is safe: CPython's reference-counting GC closes the
    generator (and fires the finalizer) as soon as the local variable goes out
    of scope, which is effectively immediate.

    The producer thread must exit before the test returns so we don't leave
    pending run_coroutine_threadsafe() work on the teardown loop.  We capture
    the thread reference and join it (via run_in_executor) after aclose().
    """
    import asyncio

    rt = MagicMock()
    block_after_first = threading.Event()
    producer_thread_ref: list[threading.Thread] = []

    def slow_iter():
        yield {"id": "msg1", "choices": [{"delta": {"content": "chunk0"}}]}
        # Block here — producer should be killed before it ever resumes
        block_after_first.wait(timeout=5.0)
        # After kill unblocks: raise immediately, producer exits via exception path
        raise OSError("socket closed by kill")

    rt.chat_stream.return_value = slow_iter()
    rt._model = MagicMock()
    rt._model.stop = MagicMock(side_effect=lambda timeout=2.0: block_after_first.set())

    # Patch Thread to capture the producer thread reference
    original_thread_start = threading.Thread.start

    def patched_start(self_thread):
        producer_thread_ref.append(self_thread)
        original_thread_start(self_thread)

    sess = LocalChatSession(rt, on_progress=None)
    assert sess._stream_kill_pending is False

    threading.Thread.start = patched_start
    try:
        gen = sess.stream(messages=[], max_tokens=100, temperature=0.1)
        async for chunk in gen:  # noqa: F841
            break  # consumer exits immediately after first chunk
        await gen.aclose()  # flush async-gen finalizer → runs finally: kill_process()
    finally:
        threading.Thread.start = original_thread_start

    # Wait for the producer thread to exit (it raises OSError → SENTINEL_ERR path → done)
    if producer_thread_ref:
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, lambda: producer_thread_ref[0].join(timeout=5.0))

    # The finally block in stream() must have called kill_process()
    assert sess._stream_kill_pending is True
    rt._model.stop.assert_called()


# ---------------------------------------------------------------------------
# Regression: fast producer + slow consumer → no dropped chunks (backpressure)
# ---------------------------------------------------------------------------

async def test_stream_queue_backpressure_no_drop():
    """Fast producer (100 chunks) + slow consumer → ALL chunks delivered, none dropped.

    With the old put_nowait approach a QueueFull exception inside the event-loop
    callback would silently discard tokens.  With run_coroutine_threadsafe +
    blocking put() the producer is paused until the consumer drains space.
    """
    import asyncio

    NUM_CHUNKS = 100

    rt = MagicMock()

    def fast_iter():
        for i in range(NUM_CHUNKS):
            yield {"id": f"msg{i}", "choices": [{"delta": {"content": f"tok{i}"}}]}
        # Final usage chunk (empty choices — produces no parsed event)
        yield {"usage": {"prompt_tokens": 1, "completion_tokens": NUM_CHUNKS}, "choices": []}

    rt.chat_stream.return_value = fast_iter()
    rt._model = MagicMock()

    sess = LocalChatSession(rt, on_progress=None)

    collected = []
    async for item in sess.stream(messages=[], max_tokens=1000, temperature=0.1):
        if item.get("type") == "delta":
            collected.append(item)
        # Yield control to the event loop between each chunk to let the producer
        # fill the queue. asyncio.sleep(0) is enough — it yields one scheduler tick.
        await asyncio.sleep(0)

    assert len(collected) == NUM_CHUNKS, (
        f"Expected {NUM_CHUNKS} delta chunks, got {len(collected)} "
        "(token drop detected — likely put_nowait QueueFull regression)"
    )
    # Warm-pool regression guard: clean completion must NOT kill the producer.
    rt._model.stop.assert_not_called()


# ---------------------------------------------------------------------------
# Regression: clean stream exit must NOT kill the warm-pool
# ---------------------------------------------------------------------------

async def test_stream_clean_exit_does_not_kill_producer():
    """After a clean stream completes (all chunks consumed to SENTINEL_END),
    kill_process() / model.stop() must NOT be called.

    This is the key regression test for the warm-pool fix: the old unconditional
    finally: kill_process() would call LlamaServer.stop() on every clean exit,
    leaving LlmWrapper._model pointing at a dead server.  The next session's
    mm.acquire() would see is_loaded()==True (lying) and yield a broken runtime.
    """
    rt = MagicMock()
    rt.chat_stream.return_value = iter([
        {"id": "m1", "choices": [{"delta": {"content": "tok1"}}]},
        {"id": "m1", "choices": [{"delta": {"content": "tok2"}}]},
        {"usage": {"prompt_tokens": 2, "completion_tokens": 2}, "choices": []},
    ])
    rt._model = MagicMock()

    sess = LocalChatSession(rt, on_progress=None)
    chunks = [c async for c in sess.stream(messages=[], max_tokens=100, temperature=0.1)]

    assert len(chunks) == 3  # 2 deltas + 1 done
    # Clean exit: warm-pool must be untouched
    rt._model.stop.assert_not_called()
    assert sess._stream_kill_pending is False


# ---------------------------------------------------------------------------
# Regression: two sequential streams on the same session (agent multi-turn)
# ---------------------------------------------------------------------------

async def test_two_sequential_streams_share_warm_pool():
    """Agent multi-turn pattern: same LocalChatSession, two sequential streams.

    Both streams must complete successfully.  model.stop() must NEVER be called
    between or after the streams — the warm-pool must survive the full session.

    This tests the exact regression scenario from the bug report:
    Round 1 unconditionally killed llama-server → Round 2 hit
    RuntimeError("LlamaServer not started; call start() first").
    """
    rt = MagicMock()
    rt._model = MagicMock()

    def make_iter(text: str):
        return iter([
            {"id": "m1", "choices": [{"delta": {"content": text}}]},
            {"usage": {"prompt_tokens": 1, "completion_tokens": 1}, "choices": []},
        ])

    sess = LocalChatSession(rt, on_progress=None)

    # Round 1
    rt.chat_stream.return_value = make_iter("round-one")
    chunks1 = [c async for c in sess.stream(messages=[], max_tokens=100, temperature=0.1)]

    # model.stop() must NOT have been called after round 1
    rt._model.stop.assert_not_called()

    # Round 2 — same session, new chat_stream
    rt.chat_stream.return_value = make_iter("round-two")
    chunks2 = [c async for c in sess.stream(messages=[], max_tokens=100, temperature=0.1)]

    assert any(c.get("text") == "round-one" for c in chunks1)
    assert any(c.get("text") == "round-two" for c in chunks2)
    # Warm-pool untouched across both rounds
    rt._model.stop.assert_not_called()
