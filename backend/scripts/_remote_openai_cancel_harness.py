"""Cancel harness for OpenAI Chat Completions + Responses streaming.

V1 fake_progress + V2 in-session _guard across both endpoints.
V3 (pre-connection on HTTPS) replaced with V3' mid-handshake abort
(spec §6.3).

Usage (preferred — uses DB):
    $env:MTX_REMOTE_CONN_ID = "<openai conn id from UI Settings>"
    uv run --project core/backend python core/backend/scripts/_remote_openai_cancel_harness.py

Usage (fallback — env-var override):
    $env:MTX_OPENAI_API_KEY = "sk-..."
    uv run --project core/backend python core/backend/scripts/_remote_openai_cancel_harness.py

Env:
    MTX_REMOTE_CONN_ID         (preferred — looks up endpoint + api_key from DB)
    MTX_OPENAI_API_KEY         (fallback when MTX_REMOTE_CONN_ID not set)
    MTX_OPENAI_ENDPOINT        (only used with env-var fallback)
    MTX_OPENAI_TEXT_MODEL=gpt-4o-mini, MTX_OPENAI_REASONING_MODEL=o4-mini

Asserts:
    V1, V2 cancel latency <3s after fire (post-first-byte).
    V3' mid-handshake abort wall-clock <5s.
"""
from __future__ import annotations
import os
import sys
import threading
import time

from _remote_smoke_helpers import resolve_provider

TEXT_MODEL = os.environ.get("MTX_OPENAI_TEXT_MODEL", "gpt-4o-mini")
REASONING_MODEL = os.environ.get("MTX_OPENAI_REASONING_MODEL", "o4-mini")

LONG_PROMPT = (
    "Write a 1500-word essay on the history of computing covering at "
    "least 10 eras with specific dates and names. Be thorough."
)


def _get_prov():
    return resolve_provider("openai", "https://api.openai.com", "MTX_OPENAI_API_KEY")


def variant_1_outer_fake_progress(model: str, label: str) -> tuple[bool, float]:
    from app.services._remote_chat import RemoteChatSession
    from app.utils.inference import fake_progress
    from app.handler.exceptions import TaskCancelledError

    prov = _get_prov()
    ev = threading.Event()

    def on_progress(progress, message):
        if ev.is_set():
            raise TaskCancelledError(f"V1[{label}] cancel")

    sess = RemoteChatSession(prov, model)

    # Fire cancel after ~2s (post-first-byte). The fake_progress poll watcher
    # picks it up on the next progress tick and raises TaskCancelledError
    # inside the chat() call.
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


def variant_2_in_session_guard(model: str, label: str) -> tuple[bool, float]:
    from app.services._remote_chat import RemoteChatSession
    from app.handler.exceptions import TaskCancelledError

    prov = _get_prov()
    ev = threading.Event()

    def on_progress(progress, message):
        if ev.is_set():
            raise TaskCancelledError(f"V2[{label}] cancel")

    sess = RemoteChatSession(prov, model, on_progress=on_progress)
    cancel_t = threading.Thread(
        target=lambda: (time.sleep(2.0), ev.set()), daemon=True,
    )
    cancel_t.start()

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


def variant_3_mid_handshake(model: str, label: str) -> tuple[bool, float]:
    """Fire kill_pending immediately, before urlopen returns. The TLS handshake
    is still in flight when kill_pending is set; the response, when stashed,
    is closed synchronously by _set_current and raises OSError.

    Wall-clock <5s expected.
    """
    from app.services._remote_chat import RemoteChatSession
    from app.handler.exceptions import RemoteApiError

    prov = _get_prov()
    sess = RemoteChatSession(prov, model)

    # Fire kill_pending IMMEDIATELY in a background thread (0ms delay)
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
    results = []
    for label, model in (("chat-completions", TEXT_MODEL),
                          ("responses", REASONING_MODEL)):
        for variant, fn in (("V1", variant_1_outer_fake_progress),
                            ("V2", variant_2_in_session_guard),
                            ("V3'", variant_3_mid_handshake)):
            try:
                ok, latency = fn(model, label)
            except Exception as e:
                ok, latency = False, -1.0
                print(f"[{variant}][{label}] ERROR: {e}")
            status = "PASS" if ok else "FAIL"
            print(f"[{variant}][{label}] {status} latency={latency:.2f}s model={model}")
            results.append(ok)

    overall = all(results)
    print(f"\n{'PASS' if overall else 'FAIL'}: {sum(results)}/{len(results)}")
    sys.exit(0 if overall else 1)
