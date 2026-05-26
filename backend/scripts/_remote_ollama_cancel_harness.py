"""Ad-hoc cancel harness: validates RemoteChatSession's cancel latency
across three call patterns.

Usage:
    uv run --project core/backend python core/backend/scripts/_remote_ollama_cancel_harness.py

Environment:
    MTX_OLLAMA_ENDPOINT (default: http://localhost:11434)
    MTX_REMOTE_LLM_MODEL (default: gpt-oss:120b)

Prereqs:
- Ollama running at MTX_OLLAMA_ENDPOINT with the model pulled.

Variants:
1. Outer fake_progress watcher (mirrors the real production call site
   in VideoSummaryService._execute via cancel_guard ContextVar
   single-poller short-circuit).
2. In-session _guard() only (RemoteChatSession's own watcher fires).
3. Pre-connection cancel -- connects to a non-listening port; cancel
   takes effect when urlopen socket timeout (30 s) expires (documented
   R7 limitation).

Asserts: <3 s cancel latency for Variants 1 & 2 (post-first-byte);
<31 s for Variant 3 (timeout-bounded).

Spec: Testing §Cancel harness.
"""
from __future__ import annotations
import gc
import os
import threading
import time
import sys
from pathlib import Path as _Path

# Bootstrap: make `app` importable when this file is run directly as a script
# (sys.path[0] is scripts/ by default; app lives one level up).
_BACKEND_DIR = str(_Path(__file__).resolve().parent.parent)
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

DEFAULT_ENDPOINT = os.environ.get("MTX_OLLAMA_ENDPOINT", "http://localhost:11434")
DEFAULT_MODEL = os.environ.get("MTX_REMOTE_LLM_MODEL", "gpt-oss:120b")
LONG_PROMPT = (
    "Write a 1500-word detailed essay about the history of computing, "
    "covering at least 10 distinct eras with concrete dates and names. "
    "Be thorough."
)


def _cancel_after(delay: float, cancel_event: threading.Event):
    def _fire():
        time.sleep(delay)
        cancel_event.set()
    t = threading.Thread(target=_fire, daemon=True)
    t.start()
    return t


def variant_1_outer_fake_progress() -> tuple[bool, float]:
    """fake_progress(cancellable=session) wraps the call. Cancel via
    setting the task id in _cancelled_ids and firing on_progress."""
    from app.adapters.ai.remote.ollama import OllamaProvider
    from app.services._remote_chat import RemoteChatSession
    from app.utils.inference import fake_progress
    from app.handler.exceptions import TaskCancelledError

    prov = OllamaProvider(DEFAULT_ENDPOINT, None)

    # Custom on_progress that raises TaskCancelledError when cancel_event is set
    cancel_event = threading.Event()
    def on_progress(progress, message):
        if cancel_event.is_set():
            raise TaskCancelledError("variant 1 cancel")

    session = RemoteChatSession(prov, DEFAULT_MODEL)

    _cancel_after(2.0, cancel_event)
    t_start_call = None

    try:
        with fake_progress(
            on_progress, 0.0, 1.0,
            "task.progress.generating", duration=600.0,
            cancellable=session,
        ):
            t_start_call = time.monotonic()
            session.chat(
                messages=[{"role": "user", "content": LONG_PROMPT}],
                max_tokens=2000, temperature=0.5,
            )
        return (False, 0.0)  # didn't raise
    except TaskCancelledError:
        t_cancel = time.monotonic()
        latency = (t_cancel - t_start_call) - 2.0  # subtract pre-cancel wait
        return (latency < 3.0, latency)


def variant_2_in_session_guard() -> tuple[bool, float]:
    """No outer fake_progress -- RemoteChatSession's own _guard() owns
    poll+kill via cancel_guard."""
    from app.adapters.ai.remote.ollama import OllamaProvider
    from app.services._remote_chat import RemoteChatSession
    from app.handler.exceptions import TaskCancelledError

    prov = OllamaProvider(DEFAULT_ENDPOINT, None)
    cancel_event = threading.Event()
    def on_progress(progress, message):
        if cancel_event.is_set():
            raise TaskCancelledError("variant 2 cancel")

    session = RemoteChatSession(
        prov, DEFAULT_MODEL,
        on_progress=on_progress,
        cancel_pct=0.5, cancel_msg="task.progress.generating",
    )

    _cancel_after(2.0, cancel_event)
    t_start = None
    try:
        t_start = time.monotonic()
        session.chat(
            messages=[{"role": "user", "content": LONG_PROMPT}],
            max_tokens=2000, temperature=0.5,
        )
        return (False, 0.0)
    except TaskCancelledError:
        latency = (time.monotonic() - t_start) - 2.0
        return (latency < 3.0, latency)


def variant_3_pre_connection() -> tuple[bool, float]:
    """Non-listening port: connect stalls. Cancel takes effect when
    urlopen's 30s socket timeout expires."""
    from app.adapters.ai.remote.ollama import OllamaProvider
    from app.services._remote_chat import RemoteChatSession
    from app.handler.exceptions import TaskCancelledError

    # Non-listening port -- connect should hang or fail.
    prov = OllamaProvider("http://localhost:1", None)
    cancel_event = threading.Event()
    def on_progress(progress, message):
        if cancel_event.is_set():
            raise TaskCancelledError("variant 3 cancel")

    session = RemoteChatSession(
        prov, DEFAULT_MODEL, on_progress=on_progress,
        cancel_pct=0.0, cancel_msg="task.progress.generating",
    )

    _cancel_after(0.1, cancel_event)
    t_start = time.monotonic()
    try:
        session.chat(
            messages=[{"role": "user", "content": "hi"}],
            max_tokens=10, temperature=0.0,
        )
        return (False, 0.0)
    except TaskCancelledError:
        latency = time.monotonic() - t_start
        # AC#4 Out-of-AC: <= urlopen_timeout + 1 = 31s
        return (latency < 31.0, latency)
    except Exception as e:
        # Acceptable: connection_failed if connect failed before cancel landed
        return (False, time.monotonic() - t_start)


def main() -> int:
    print(f"[setup] endpoint={DEFAULT_ENDPOINT} model={DEFAULT_MODEL}")
    print()
    print("Variant 1: outer fake_progress watcher")
    ok1, lat1 = variant_1_outer_fake_progress()
    print(f"  result: ok={ok1} latency={lat1:.2f}s (threshold 3.0s)")

    gc.collect()
    print("\nVariant 2: in-session _guard()")
    ok2, lat2 = variant_2_in_session_guard()
    print(f"  result: ok={ok2} latency={lat2:.2f}s (threshold 3.0s)")

    gc.collect()
    print("\nVariant 3: pre-connection cancel")
    ok3, lat3 = variant_3_pre_connection()
    print(f"  result: ok={ok3} latency={lat3:.2f}s (threshold 31.0s)")

    overall = ok1 and ok2 and ok3
    print(f"\nOVERALL: {'PASS' if overall else 'FAIL'}")
    return 0 if overall else 1


if __name__ == "__main__":
    sys.exit(main())
