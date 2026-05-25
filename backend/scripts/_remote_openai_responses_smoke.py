"""Ad-hoc smoke for OpenAI Responses API (o4-mini; blocking + streaming).

Usage (preferred — uses DB):
    $env:MTX_REMOTE_CONN_ID = "<openai conn id from UI Settings>"
    uv run --project core/backend python core/backend/scripts/_remote_openai_responses_smoke.py

Usage (fallback — env-var override):
    $env:MTX_OPENAI_API_KEY = "sk-..."
    uv run --project core/backend python core/backend/scripts/_remote_openai_responses_smoke.py

Env:
    MTX_REMOTE_CONN_ID         (preferred — looks up endpoint + api_key from DB)
    MTX_OPENAI_API_KEY         (fallback when MTX_REMOTE_CONN_ID not set)
    MTX_OPENAI_ENDPOINT        (only used with env-var fallback; default: https://api.openai.com)
    MTX_OPENAI_REASONING_MODEL (default: o4-mini)
"""
from __future__ import annotations
import os
import sys
import time

from _remote_smoke_helpers import resolve_provider

MODEL = os.environ.get("MTX_OPENAI_REASONING_MODEL", "o4-mini")


def _get_prov():
    return resolve_provider("openai", "https://api.openai.com", "MTX_OPENAI_API_KEY")


def smoke_blocking():
    prov = _get_prov()
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
    prov = _get_prov()
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
    passes = []
    for fn in (smoke_blocking, smoke_streaming):
        try:
            passes.append(fn())
        except Exception as e:
            print(f"[FAIL] {fn.__name__}: {e}")
            passes.append(False)
    print(f"\n{'PASS' if all(passes) else 'FAIL'}: {sum(passes)}/{len(passes)}")
    sys.exit(0 if all(passes) else 1)
