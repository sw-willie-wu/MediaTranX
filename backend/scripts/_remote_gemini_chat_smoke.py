"""Ad-hoc smoke for Gemini chat (text + vision; blocking + streaming).

Usage (preferred — uses DB):
    $env:MTX_REMOTE_CONN_ID = "<gemini conn id from UI Settings>"
    uv run --project core/backend python core/backend/scripts/_remote_gemini_chat_smoke.py

Usage (fallback — env-var override):
    $env:MTX_GEMINI_API_KEY = "AIza..."
    uv run --project core/backend python core/backend/scripts/_remote_gemini_chat_smoke.py

Env:
    MTX_REMOTE_CONN_ID    (preferred — looks up endpoint + api_key from DB)
    MTX_GEMINI_API_KEY    (fallback when MTX_REMOTE_CONN_ID not set)
    MTX_GEMINI_ENDPOINT   (only used with env-var fallback; default: https://generativelanguage.googleapis.com)
    MTX_GEMINI_MODEL      (default: gemini-2.5-flash)
"""
from __future__ import annotations
import os
import sys
import time

from _remote_smoke_helpers import resolve_provider

MODEL = os.environ.get("MTX_GEMINI_MODEL", "gemini-2.5-flash")


def _make_test_image_part():
    from PIL import Image
    import io, base64
    img = Image.new("RGB", (32, 32), color="green")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("ascii")


def _get_prov():
    return resolve_provider(
        "gemini",
        "https://generativelanguage.googleapis.com",
        "MTX_GEMINI_API_KEY",
    )


def smoke_text_blocking():
    prov = _get_prov()
    t0 = time.monotonic()
    result = prov.chat(
        model=MODEL,
        messages=[{"role": "user", "content": "Say 'PONG' and nothing else."}],
        max_tokens=10, temperature=0.0, task="frame_select",
    )
    print(f"[text-blocking] {time.monotonic() - t0:.2f}s | {result!r}")
    return "pong" in result.lower()


def smoke_text_streaming():
    prov = _get_prov()
    t0 = time.monotonic()
    result = prov.chat(
        model=MODEL,
        messages=[{"role": "user", "content": "Say 'PONG' and nothing else."}],
        max_tokens=10, temperature=0.0,
        abort_hook=lambda r: None, task="frame_select",
    )
    print(f"[text-streaming] {time.monotonic() - t0:.2f}s | {result!r}")
    return "pong" in result.lower()


def smoke_vision_streaming():
    prov = _get_prov()
    b64 = _make_test_image_part()
    messages = [{
        "role": "user",
        "content": [
            {"type": "text", "text": "What color dominates? One word."},
            {"type": "image", "mime_type": "image/png", "data": b64},
        ],
    }]
    t0 = time.monotonic()
    result = prov.chat(
        model=MODEL, messages=messages,
        max_tokens=10, temperature=0.0,
        abort_hook=lambda r: None, task="frame_select",
    )
    print(f"[vision-streaming] {time.monotonic() - t0:.2f}s | {result!r}")
    return "green" in result.lower()


if __name__ == "__main__":
    passes = []
    for fn in (smoke_text_blocking, smoke_text_streaming, smoke_vision_streaming):
        try:
            passes.append(fn())
        except Exception as e:
            print(f"[FAIL] {fn.__name__}: {e}")
            passes.append(False)
    print(f"\n{'PASS' if all(passes) else 'FAIL'}: {sum(passes)}/{len(passes)}")
    sys.exit(0 if all(passes) else 1)
