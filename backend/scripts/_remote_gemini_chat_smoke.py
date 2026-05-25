"""Ad-hoc smoke for Gemini chat (text + vision; blocking + streaming).

Usage:
    $env:MTX_GEMINI_API_KEY = "AIza..."
    uv run --project core/backend python core/backend/scripts/_remote_gemini_chat_smoke.py

Env:
    MTX_GEMINI_API_KEY (required)
    MTX_GEMINI_ENDPOINT (default: https://generativelanguage.googleapis.com)
    MTX_GEMINI_MODEL (default: gemini-2.5-flash)
"""
from __future__ import annotations
import os
import sys
import time

ENDPOINT = os.environ.get(
    "MTX_GEMINI_ENDPOINT", "https://generativelanguage.googleapis.com"
)
API_KEY = os.environ.get("MTX_GEMINI_API_KEY")
MODEL = os.environ.get("MTX_GEMINI_MODEL", "gemini-2.5-flash")


def _make_test_image_part():
    from PIL import Image
    import io, base64
    img = Image.new("RGB", (32, 32), color="green")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("ascii")


def smoke_text_blocking():
    from app.adapters.ai.remote.gemini import GeminiProvider
    prov = GeminiProvider(ENDPOINT, API_KEY)
    t0 = time.monotonic()
    result = prov.chat(
        model=MODEL,
        messages=[{"role": "user", "content": "Say 'PONG' and nothing else."}],
        max_tokens=10, temperature=0.0,
    )
    print(f"[text-blocking] {time.monotonic() - t0:.2f}s | {result!r}")
    return "pong" in result.lower()


def smoke_text_streaming():
    from app.adapters.ai.remote.gemini import GeminiProvider
    prov = GeminiProvider(ENDPOINT, API_KEY)
    t0 = time.monotonic()
    result = prov.chat(
        model=MODEL,
        messages=[{"role": "user", "content": "Say 'PONG' and nothing else."}],
        max_tokens=10, temperature=0.0,
        abort_hook=lambda r: None,
    )
    print(f"[text-streaming] {time.monotonic() - t0:.2f}s | {result!r}")
    return "pong" in result.lower()


def smoke_vision_streaming():
    from app.adapters.ai.remote.gemini import GeminiProvider
    prov = GeminiProvider(ENDPOINT, API_KEY)
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
        abort_hook=lambda r: None,
    )
    print(f"[vision-streaming] {time.monotonic() - t0:.2f}s | {result!r}")
    return "green" in result.lower()


if __name__ == "__main__":
    if not API_KEY:
        print("ERROR: MTX_GEMINI_API_KEY not set", file=sys.stderr)
        sys.exit(2)
    passes = []
    for fn in (smoke_text_blocking, smoke_text_streaming, smoke_vision_streaming):
        try:
            passes.append(fn())
        except Exception as e:
            print(f"[FAIL] {fn.__name__}: {e}")
            passes.append(False)
    print(f"\n{'PASS' if all(passes) else 'FAIL'}: {sum(passes)}/{len(passes)}")
    sys.exit(0 if all(passes) else 1)
