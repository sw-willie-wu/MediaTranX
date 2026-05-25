"""Ad-hoc smoke for OpenAI Responses API (o4-mini; blocking + streaming).

Usage:
    $env:MTX_OPENAI_API_KEY = "sk-..."
    uv run --project core/backend python core/backend/scripts/_remote_openai_responses_smoke.py

Env:
    MTX_OPENAI_API_KEY (required)
    MTX_OPENAI_ENDPOINT (default: https://api.openai.com)
    MTX_OPENAI_REASONING_MODEL (default: o4-mini)
"""
from __future__ import annotations
import os
import sys
import time

ENDPOINT = os.environ.get("MTX_OPENAI_ENDPOINT", "https://api.openai.com")
API_KEY = os.environ.get("MTX_OPENAI_API_KEY")
MODEL = os.environ.get("MTX_OPENAI_REASONING_MODEL", "o4-mini")


def smoke_blocking():
    from app.adapters.ai.remote.openai import OpenAIProvider
    prov = OpenAIProvider(ENDPOINT, API_KEY)
    t0 = time.monotonic()
    result = prov.chat(
        model=MODEL,
        messages=[{"role": "user", "content": "What is 2+2? One number only."}],
        max_tokens=50,  # reasoning models need headroom for thinking tokens
        temperature=0.0,
    )
    print(f"[responses-blocking] {time.monotonic() - t0:.2f}s | {result!r}")
    return "4" in result


def smoke_streaming():
    from app.adapters.ai.remote.openai import OpenAIProvider
    prov = OpenAIProvider(ENDPOINT, API_KEY)
    t0 = time.monotonic()
    result = prov.chat(
        model=MODEL,
        messages=[{"role": "user", "content": "What is 2+2? One number only."}],
        max_tokens=50, temperature=0.0,
        abort_hook=lambda r: None,
    )
    print(f"[responses-streaming] {time.monotonic() - t0:.2f}s | {result!r}")
    return "4" in result


if __name__ == "__main__":
    if not API_KEY:
        print("ERROR: MTX_OPENAI_API_KEY not set", file=sys.stderr)
        sys.exit(2)
    passes = []
    for fn in (smoke_blocking, smoke_streaming):
        try:
            passes.append(fn())
        except Exception as e:
            print(f"[FAIL] {fn.__name__}: {e}")
            passes.append(False)
    print(f"\n{'PASS' if all(passes) else 'FAIL'}: {sum(passes)}/{len(passes)}")
    sys.exit(0 if all(passes) else 1)
