"""Cancel harness for Gemini streaming.

V1 fake_progress + V2 in-session _guard + V3' mid-handshake abort.

Usage:
    uv run --project core/backend python core/backend/scripts/_remote_gemini_cancel_harness.py

Env:
    MTX_GEMINI_API_KEY, MTX_GEMINI_ENDPOINT,
    MTX_GEMINI_MODEL=gemini-2.5-flash

Asserts:
    V1, V2 cancel <3s after fire (post-first-byte).
    V3' mid-handshake <5s.
"""
from __future__ import annotations
import os
import sys
import threading
import time

ENDPOINT = os.environ.get(
    "MTX_GEMINI_ENDPOINT", "https://generativelanguage.googleapis.com"
)
API_KEY = os.environ.get("MTX_GEMINI_API_KEY")
MODEL = os.environ.get("MTX_GEMINI_MODEL", "gemini-2.5-flash")

LONG_PROMPT = (
    "Write a 1500-word essay on the history of computing covering at "
    "least 10 eras with specific dates and names. Be thorough."
)


def variant_1():
    from app.adapters.ai.remote.gemini import GeminiProvider
    from app.services._remote_chat import RemoteChatSession
    from app.utils.inference import fake_progress
    from app.handler.exceptions import TaskCancelledError

    prov = GeminiProvider(ENDPOINT, API_KEY)
    ev = threading.Event()

    def on_progress(progress, message):
        if ev.is_set():
            raise TaskCancelledError("V1 cancel")

    sess = RemoteChatSession(prov, MODEL)
    threading.Thread(
        target=lambda: (time.sleep(2.0), ev.set()), daemon=True,
    ).start()

    t_start = None
    try:
        with fake_progress(
            on_progress, 0.0, 1.0,
            "task.progress.generating", duration=600.0,
            cancellable=sess,
        ):
            t_start = time.monotonic()
            sess.chat(
                messages=[{"role": "user", "content": LONG_PROMPT}],
                max_tokens=2000, temperature=0.5,
            )
        return False, 0.0
    except TaskCancelledError:
        latency = time.monotonic() - t_start - 2.0
        return latency < 3.0, latency


def variant_2():
    from app.adapters.ai.remote.gemini import GeminiProvider
    from app.services._remote_chat import RemoteChatSession
    from app.handler.exceptions import TaskCancelledError

    prov = GeminiProvider(ENDPOINT, API_KEY)
    ev = threading.Event()

    def on_progress(progress, message):
        if ev.is_set():
            raise TaskCancelledError("V2 cancel")

    sess = RemoteChatSession(prov, MODEL, on_progress=on_progress)
    threading.Thread(
        target=lambda: (time.sleep(2.0), ev.set()), daemon=True,
    ).start()

    t_start = None
    try:
        t_start = time.monotonic()
        sess.chat(
            messages=[{"role": "user", "content": LONG_PROMPT}],
            max_tokens=2000, temperature=0.5,
        )
        return False, 0.0
    except TaskCancelledError:
        latency = time.monotonic() - t_start - 2.0
        return latency < 3.0, latency


def variant_3():
    from app.adapters.ai.remote.gemini import GeminiProvider
    from app.services._remote_chat import RemoteChatSession
    from app.handler.exceptions import RemoteApiError

    prov = GeminiProvider(ENDPOINT, API_KEY)
    sess = RemoteChatSession(prov, MODEL)
    threading.Thread(target=sess.kill_process, daemon=True).start()

    t_start = time.monotonic()
    try:
        sess.chat(
            messages=[{"role": "user", "content": LONG_PROMPT}],
            max_tokens=2000, temperature=0.5,
        )
        return False, time.monotonic() - t_start
    except RemoteApiError:
        return (time.monotonic() - t_start) < 5.0, time.monotonic() - t_start


if __name__ == "__main__":
    if not API_KEY:
        print("ERROR: MTX_GEMINI_API_KEY not set", file=sys.stderr)
        sys.exit(2)
    results = []
    for name, fn in (("V1", variant_1), ("V2", variant_2), ("V3'", variant_3)):
        try:
            ok, lat = fn()
        except Exception as e:
            ok, lat = False, -1.0
            print(f"[{name}] ERROR: {e}")
        print(f"[{name}] {'PASS' if ok else 'FAIL'} latency={lat:.2f}s")
        results.append(ok)
    print(f"\n{'PASS' if all(results) else 'FAIL'}: {sum(results)}/{len(results)}")
    sys.exit(0 if all(results) else 1)
