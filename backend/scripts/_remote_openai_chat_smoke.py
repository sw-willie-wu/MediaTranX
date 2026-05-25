"""Ad-hoc smoke for OpenAI Chat Completions (text + vision; blocking + streaming).

Usage:
    $env:MTX_OPENAI_API_KEY = "sk-..."
    uv run --project core/backend python core/backend/scripts/_remote_openai_chat_smoke.py

Env:
    MTX_OPENAI_API_KEY (required)
    MTX_OPENAI_ENDPOINT (default: https://api.openai.com)
    MTX_OPENAI_TEXT_MODEL (default: gpt-4o-mini)
"""
from __future__ import annotations
import base64
import io
import os
import sys
import time

ENDPOINT = os.environ.get("MTX_OPENAI_ENDPOINT", "https://api.openai.com")
API_KEY = os.environ.get("MTX_OPENAI_API_KEY")
MODEL = os.environ.get("MTX_OPENAI_TEXT_MODEL", "gpt-4o-mini")


def _make_test_image_b64() -> tuple[str, str]:
    from PIL import Image
    img = Image.new("RGB", (32, 32), color="red")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("ascii"), "image/png"


def smoke_text_blocking():
    from app.adapters.ai.remote.openai import OpenAIProvider
    prov = OpenAIProvider(ENDPOINT, API_KEY)
    t0 = time.monotonic()
    result = prov.chat(
        model=MODEL,
        messages=[{"role": "user", "content": "Say 'PONG' and nothing else."}],
        max_tokens=10, temperature=0.0,
    )
    print(f"[text-blocking] {time.monotonic() - t0:.2f}s | {result!r}")
    return "pong" in result.lower()


def smoke_text_streaming():
    from app.adapters.ai.remote.openai import OpenAIProvider
    prov = OpenAIProvider(ENDPOINT, API_KEY)
    t0 = time.monotonic()
    result = prov.chat(
        model=MODEL,
        messages=[{"role": "user", "content": "Say 'PONG' and nothing else."}],
        max_tokens=10, temperature=0.0,
        abort_hook=lambda r: None,
    )
    print(f"[text-streaming] {time.monotonic() - t0:.2f}s | {result!r}")
    return "pong" in result.lower()


def smoke_vision_blocking():
    from app.adapters.ai.remote.openai import OpenAIProvider
    prov = OpenAIProvider(ENDPOINT, API_KEY)
    b64, mime = _make_test_image_b64()
    messages = [{
        "role": "user",
        "content": [
            {"type": "text", "text": "What color dominates this image? One word."},
            {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}},
        ],
    }]
    t0 = time.monotonic()
    result = prov.chat(
        model=MODEL, messages=messages,
        max_tokens=10, temperature=0.0,
    )
    print(f"[vision-blocking] {time.monotonic() - t0:.2f}s | {result!r}")
    return "red" in result.lower()


def smoke_vision_streaming():
    from app.adapters.ai.remote.openai import OpenAIProvider
    prov = OpenAIProvider(ENDPOINT, API_KEY)
    b64, mime = _make_test_image_b64()
    messages = [{
        "role": "user",
        "content": [
            {"type": "text", "text": "What color dominates this image? One word."},
            {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}},
        ],
    }]
    t0 = time.monotonic()
    result = prov.chat(
        model=MODEL, messages=messages,
        max_tokens=10, temperature=0.0,
        abort_hook=lambda r: None,
    )
    print(f"[vision-streaming] {time.monotonic() - t0:.2f}s | {result!r}")
    return "red" in result.lower()


if __name__ == "__main__":
    if not API_KEY:
        print("ERROR: MTX_OPENAI_API_KEY not set", file=sys.stderr)
        sys.exit(2)
    passes = []
    for fn in (smoke_text_blocking, smoke_text_streaming,
               smoke_vision_blocking, smoke_vision_streaming):
        try:
            passes.append(fn())
        except Exception as e:
            print(f"[FAIL] {fn.__name__}: {e}")
            passes.append(False)
    print(f"\n{'PASS' if all(passes) else 'FAIL'}: {sum(passes)}/{len(passes)}")
    sys.exit(0 if all(passes) else 1)
