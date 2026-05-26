"""Ad-hoc smoke for OpenAI Chat Completions (text + vision; blocking + streaming).

Usage (preferred — uses DB):
    $env:MTX_REMOTE_CONN_ID = "<openai conn id from UI Settings>"
    uv run --project core/backend python core/backend/scripts/_remote_openai_chat_smoke.py

Usage (fallback — env-var override):
    $env:MTX_OPENAI_API_KEY = "sk-..."
    uv run --project core/backend python core/backend/scripts/_remote_openai_chat_smoke.py

Env:
    MTX_REMOTE_CONN_ID    (preferred — looks up endpoint + api_key from
                           api_connections table; UI: Settings → Remote AI)
    MTX_OPENAI_API_KEY    (fallback when MTX_REMOTE_CONN_ID not set)
    MTX_OPENAI_ENDPOINT   (only used with env-var fallback; default: https://api.openai.com)
    MTX_OPENAI_TEXT_MODEL (default: gpt-4o-mini)
"""
from __future__ import annotations
import base64
import io
import os
import sys
import time

from _remote_smoke_helpers import resolve_provider

MODEL = os.environ.get("MTX_OPENAI_TEXT_MODEL", "gpt-4o-mini")


def _make_test_image_b64() -> tuple[str, str]:
    from PIL import Image
    img = Image.new("RGB", (32, 32), color="red")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("ascii"), "image/png"


def _get_prov():
    return resolve_provider("openai", "https://api.openai.com", "MTX_OPENAI_API_KEY")


def smoke_text_blocking():
    prov = _get_prov()
    t0 = time.monotonic()
    result = prov.chat(
        model=MODEL,
        messages=[{"role": "user", "content": "Say 'PONG' and nothing else."}],
        max_tokens=10, temperature=0.0,
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
        abort_hook=lambda r: None,
    )
    print(f"[text-streaming] {time.monotonic() - t0:.2f}s | {result!r}")
    return "pong" in result.lower()


def smoke_vision_blocking():
    prov = _get_prov()
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
    prov = _get_prov()
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
