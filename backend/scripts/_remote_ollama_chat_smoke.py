"""Ad-hoc real-AI smoke: OllamaProvider.chat() text path against a
running Ollama instance.

Usage:
    uv run --project core/backend python core/backend/scripts/_remote_ollama_chat_smoke.py

Environment:
    MTX_OLLAMA_ENDPOINT (default: http://localhost:11434)
    MTX_REMOTE_LLM_MODEL (default: gpt-oss:120b)

Prereqs:
- Ollama running at MTX_OLLAMA_ENDPOINT
- The chosen LLM model pulled

Asserts a non-empty response. Prints latency. Exits non-zero on failure.

NOT a pytest test — kept out of the unit suite per the Wave-H pattern
(real-AI scripts are ad-hoc, run by the operator).

Spec: Testing §Real-AI smoke.
"""
from __future__ import annotations
import os
import sys
import time


def main() -> int:
    from app.adapters.ai.remote.ollama import OllamaProvider

    endpoint = os.environ.get("MTX_OLLAMA_ENDPOINT", "http://localhost:11434")
    model = os.environ.get("MTX_REMOTE_LLM_MODEL", "gpt-oss:120b")
    print(f"[setup] endpoint={endpoint} model={model}")

    prov = OllamaProvider(endpoint, None)

    # Legacy _chat_blocking path (no abort_hook)
    t0 = time.monotonic()
    result = prov.chat(
        model=model,
        messages=[{"role": "user", "content": "Say 'hello world' in one sentence."}],
        max_tokens=100, temperature=0.0,
    )
    dt = time.monotonic() - t0
    print(f"[chat blocking] elapsed={dt:.2f}s len={len(result)} reply={result!r}")
    if not result.strip():
        print("FAIL: empty response (blocking path)", file=sys.stderr)
        return 1

    # New _chat_streaming path (abort_hook supplied)
    t0 = time.monotonic()
    result2 = prov.chat(
        model=model,
        messages=[{"role": "user", "content": "Count from 1 to 5, one per line."}],
        max_tokens=200, temperature=0.0,
        abort_hook=lambda r: None,
    )
    dt = time.monotonic() - t0
    print(f"[chat streaming] elapsed={dt:.2f}s len={len(result2)} reply={result2!r}")
    if not result2.strip():
        print("FAIL: empty response (streaming path)", file=sys.stderr)
        return 1

    print("PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
