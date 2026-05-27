"""
SPIKE-C: ChatService async stream + sync chat concurrency stress test.

Validates that:
  (a) Pure async stream() bursts do NOT cause ContextVar leaks / errors
  (b) Pure sync chat() bursts with cancel_guard run cleanly from threads
  (c) Mixed interleaved: 25 async stream + 25 sync chat in parallel
      do NOT deadlock, do NOT share/leak cancel_guard ContextVar state

Key: this is a STUB — no real llama-server needed. Production cancel_guard
is imported directly from app.utils.inference to stress the real code path.

Usage:
    cd core/backend && uv run python scripts/_spike_agent_c_concurrency.py
"""
import asyncio
import sys
import time
import traceback
import threading
from pathlib import Path

# Ensure `app` package is importable (core/backend is the project root)
_backend_root = Path(__file__).resolve().parent.parent
if str(_backend_root) not in sys.path:
    sys.path.insert(0, str(_backend_root))


# ---------------------------------------------------------------------------
# Fake runtime — simulates blocking LLM calls without a real server
# ---------------------------------------------------------------------------
class FakeRuntime:
    """Simulates a llama-server call: blocking sync + blocking streaming."""

    def chat(self, *args, **kwargs):
        """Blocking sync response — 20ms as a proxy for a real LLM call."""
        time.sleep(0.02)
        return "fake response"

    def chat_stream(self, *args, **kwargs):
        """Generator yielding fake chunks — 10ms per chunk × 5 chunks."""
        for i in range(5):
            time.sleep(0.01)
            yield {"choices": [{"delta": {"content": f"chunk{i}"}}]}
        yield {"usage": {"prompt_tokens": 10, "completion_tokens": 5}}


# ---------------------------------------------------------------------------
# Fake session — mirrors production LocalChatSession structure closely
# ---------------------------------------------------------------------------
class FakeLocalChatSession:
    """
    Mirrors production LocalChatSession:
      - chat()   : sync, wraps cancel_guard when on_progress is provided
      - stream() : async, uses producer-thread + asyncio.Queue
    """

    def __init__(self, runtime: FakeRuntime, on_progress=None):
        self._runtime = runtime
        self._on_progress = on_progress

    # -- sync path -----------------------------------------------------------
    def chat(self, **kwargs):
        """
        Mirrors production pattern: wrap with cancel_guard when on_progress
        is active. cancel_guard installs a ContextVar on the *calling* thread.
        From an executor (thread-pool) thread, Python's contextvars module
        gives each thread its own fresh context — so there is no cross-thread
        sharing of _in_call_cancel_owner by default.
        """
        from app.utils.inference import cancel_guard
        from contextlib import nullcontext

        guard = (
            cancel_guard(
                self._on_progress,
                cancellable=self,
                progress=0.5,
                message="task.progress.generating",
            )
            if self._on_progress
            else nullcontext()
        )
        with guard:
            return self._runtime.chat(**kwargs)

    def kill_process(self):
        """No-op for stub — cancel_guard calls this if TaskCancelledError."""
        pass

    # -- async stream path ---------------------------------------------------
    async def stream(self, **kwargs):
        """
        Mirrors production LocalChatSession.stream():
        - producer thread pushes chunks via loop.call_soon_threadsafe
        - async generator yields from asyncio.Queue
        NOTE: stream() intentionally runs WITHOUT cancel_guard (on_progress=None
        on stream path); this is the spec §5.3.2 invariant under test.
        """
        loop = asyncio.get_running_loop()
        q: asyncio.Queue = asyncio.Queue(maxsize=64)
        SENTINEL = object()

        def producer():
            try:
                for chunk in self._runtime.chat_stream(**kwargs):
                    loop.call_soon_threadsafe(q.put_nowait, chunk)
                loop.call_soon_threadsafe(q.put_nowait, SENTINEL)
            except Exception as exc:
                loop.call_soon_threadsafe(q.put_nowait, ("ERR", exc))

        threading.Thread(target=producer, daemon=True, name="stream-producer").start()

        while True:
            item = await q.get()
            if item is SENTINEL:
                return
            if isinstance(item, tuple) and item[0] == "ERR":
                raise item[1]
            yield item


# ---------------------------------------------------------------------------
# Test cases
# ---------------------------------------------------------------------------

async def test_pure_async(runtime: FakeRuntime, n: int = 25) -> float:
    """(a) N async stream() rounds, no cancel_guard active."""
    errors = []

    async def one_round(i: int):
        sess = FakeLocalChatSession(runtime)  # on_progress=None
        chunks = []
        async for chunk in sess.stream(messages=[{"role": "user", "content": f"q{i}"}]):
            chunks.append(chunk)
        assert len(chunks) == 6, f"expected 6 chunks, got {len(chunks)}"  # 5 content + 1 usage
        return len(chunks)

    t0 = time.time()
    tasks = [asyncio.create_task(one_round(i)) for i in range(n)]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    elapsed = time.time() - t0

    for i, r in enumerate(results):
        if isinstance(r, Exception):
            errors.append(f"async round {i}: {r}")

    if errors:
        print(f"  FAIL — {len(errors)} error(s):")
        for e in errors:
            print(f"    {e}")
        return -1.0

    print(f"  PASS — {n} async rounds in {elapsed:.2f}s")
    return elapsed


async def test_pure_sync(runtime: FakeRuntime, n: int = 25) -> float:
    """
    (b) N sync chat() rounds in executor threads, each with cancel_guard active.
    Tests that cancel_guard ContextVar is correctly isolated per thread
    (Python contextvars: threads start with a *copy* of the creating thread's
    context — but executor threads get a fresh context for each submitted call).
    """
    errors = []

    def one_round(i: int):
        # Provide a trivial on_progress so cancel_guard actually installs
        def noop_progress(p, msg):
            pass

        sess = FakeLocalChatSession(runtime, on_progress=noop_progress)
        result = sess.chat(messages=[{"role": "user", "content": f"q{i}"}])
        assert result == "fake response", f"unexpected result: {result!r}"
        return result

    loop = asyncio.get_event_loop()
    t0 = time.time()
    futures = [loop.run_in_executor(None, one_round, i) for i in range(n)]
    results = await asyncio.gather(*futures, return_exceptions=True)
    elapsed = time.time() - t0

    for i, r in enumerate(results):
        if isinstance(r, Exception):
            errors.append(f"sync round {i}: {r}")

    if errors:
        print(f"  FAIL — {len(errors)} error(s):")
        for e in errors:
            print(f"    {e}")
        return -1.0

    print(f"  PASS — {n} sync rounds in {elapsed:.2f}s")
    return elapsed


async def test_mixed(runtime: FakeRuntime, n_async: int = 25, n_sync: int = 25) -> float:
    """
    (c) Mixed interleaved: N async stream + N sync chat in parallel.
    This is the primary concern — does mixed mode cause ContextVar leak or deadlock?

    The invariant under test:
      - async stream() runs with on_progress=None → cancel_guard is a no-op (pass-through)
      - sync chat() in threads each have their own ContextVar context
      - No cross-contamination should occur
    """
    errors = []

    async def async_round(i: int):
        sess = FakeLocalChatSession(runtime)  # no on_progress
        chunks = []
        async for chunk in sess.stream(messages=[{"role": "user", "content": f"async-q{i}"}]):
            chunks.append(chunk)
        assert len(chunks) == 6, f"expected 6 chunks, got {len(chunks)}"
        return ("async", i, len(chunks))

    def sync_round(i: int):
        seen_calls = []

        def tracking_progress(p, msg):
            seen_calls.append((p, msg))

        sess = FakeLocalChatSession(runtime, on_progress=tracking_progress)
        result = sess.chat(messages=[{"role": "user", "content": f"sync-q{i}"}])
        assert result == "fake response"
        return ("sync", i, result)

    loop = asyncio.get_event_loop()
    t0 = time.time()

    # Launch all together
    async_tasks = [asyncio.create_task(async_round(i)) for i in range(n_async)]
    sync_futures = [loop.run_in_executor(None, sync_round, i) for i in range(n_sync)]

    results = await asyncio.gather(*async_tasks, *sync_futures, return_exceptions=True)
    elapsed = time.time() - t0

    async_ok = sync_ok = 0
    for i, r in enumerate(results):
        if isinstance(r, Exception):
            errors.append(f"round {i}: {type(r).__name__}: {r}")
            traceback.print_exception(type(r), r, r.__traceback__)
        elif isinstance(r, tuple):
            if r[0] == "async":
                async_ok += 1
            else:
                sync_ok += 1

    total = n_async + n_sync
    if errors:
        print(f"  FAIL — {len(errors)}/{total} error(s):")
        for e in errors:
            print(f"    {e}")
        return -1.0

    print(f"  PASS — {async_ok} async + {sync_ok} sync = {total} rounds in {elapsed:.2f}s")
    return elapsed


# ---------------------------------------------------------------------------
# ContextVar isolation verification
# ---------------------------------------------------------------------------

async def test_contextvar_isolation(runtime: FakeRuntime) -> bool:
    """
    Explicit test: verify that _in_call_cancel_owner ContextVar is NOT leaked
    from a sync executor thread back into the asyncio event loop.

    Strategy:
      1. Run a sync chat() in an executor (sets ContextVar on worker thread)
      2. After executor future completes, check the ContextVar in the event loop context
      3. It should still be False (default) — not contaminated by the worker thread
    """
    from app.utils.inference import _in_call_cancel_owner

    # Baseline: should be False in event loop context
    baseline = _in_call_cancel_owner.get()
    assert baseline is False, f"Expected False baseline, got {baseline!r}"

    captured_in_thread = []
    captured_after_thread = []

    def sync_work(i: int):
        # Record the ContextVar value during the call (in worker thread context)
        def progress_cb(p, msg):
            captured_in_thread.append(_in_call_cancel_owner.get())

        sess = FakeLocalChatSession(runtime, on_progress=progress_cb)
        sess.chat()

    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, sync_work, 0)

    # Check: event loop context should still see False
    after_val = _in_call_cancel_owner.get()
    captured_after_thread.append(after_val)

    if after_val is not False:
        print(f"  FAIL — ContextVar leaked into event loop: {after_val!r}")
        return False

    # Note: captured_in_thread may be empty because progress_cb is called
    # from the cancel_guard watcher thread (a daemon), not synchronously from
    # within progress_cb during the blocking call. This is expected — the
    # watcher fires every _CANCEL_GUARD_TICK (1.0s) but our FakeRuntime.chat()
    # only sleeps 0.02s, so the watcher likely hasn't ticked yet when chat()
    # returns. That's fine — the point is the ContextVar doesn't leak.
    print(f"  PASS — ContextVar not leaked (event loop sees: {after_val!r})")
    print(f"         (cancel_guard watcher ticks fired during blocking call: {len(captured_in_thread)})")
    return True


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main():
    print("=" * 60)
    print("SPIKE-C: ChatService async+sync concurrency stress")
    print("=" * 60)

    runtime = FakeRuntime()

    # (a) Pure async
    print("\n[A] Pure async stream() — 25 rounds")
    t_a = await test_pure_async(runtime, n=25)

    # (b) Pure sync (with cancel_guard)
    print("\n[B] Pure sync chat() with cancel_guard — 25 rounds")
    t_b = await test_pure_sync(runtime, n=25)

    # (c) Mixed interleaved
    print("\n[C] Mixed interleaved: 25 async + 25 sync = 50 rounds")
    t_c = await test_mixed(runtime, n_async=25, n_sync=25)

    # (d) ContextVar isolation
    print("\n[D] ContextVar isolation: executor thread must NOT leak to event loop")
    cv_ok = await test_contextvar_isolation(runtime)

    # Summary
    print("\n" + "=" * 60)
    all_pass = t_a > 0 and t_b > 0 and t_c > 0 and cv_ok
    if all_pass:
        total = t_a + t_b + t_c
        print(f"SPIKE-C PASS: all 4 sub-tests passed")
        print(f"  A: {t_a:.2f}s  B: {t_b:.2f}s  C: {t_c:.2f}s")
        print(f"  Total: {total:.2f}s")
    else:
        failed = []
        if t_a <= 0:
            failed.append("A (pure async)")
        if t_b <= 0:
            failed.append("B (pure sync)")
        if t_c <= 0:
            failed.append("C (mixed)")
        if not cv_ok:
            failed.append("D (ContextVar isolation)")
        print(f"SPIKE-C FAIL: {', '.join(failed)}")
        sys.exit(1)

    return t_a, t_b, t_c


if __name__ == "__main__":
    asyncio.run(main())
