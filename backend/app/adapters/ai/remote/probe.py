"""Provider-level diagnostic probes.

Send a small canary request to a remote provider and report back a
structured result — used to enrich error reporting when a real chat
mysteriously fails. The 2026-05-26 LAN-proxy summary run is the
motivating case: every VLM frame pick returned `backend returned 500`
with the actual cause buried inside the proxy's `detail` field. Probes
exist so the diagnostic path is reproducible — not buried inside an
ad-hoc script that has to be re-discovered each time.

Never raises — failures become `ProbeResult(success=False, ...)` so
callers (error handlers, CLI wrappers, future API endpoints) can handle
the result uniformly.

Currently exposes only `probe_ollama_vlm`. OpenAI / Gemini equivalents
are straightforward follow-ups when those providers exhibit opaque
failures of their own.
"""
from __future__ import annotations

import base64
import io
import time
from dataclasses import dataclass
from typing import Optional

# Default canary prompt — short, generic, won't trip safety filters.
_PROBE_PROMPT = "Describe this image briefly."


@dataclass
class ProbeResult:
    """Structured probe outcome. `success=True` → `detail` holds a snippet
    of the model's response. `success=False` → `code` is the RemoteApiError
    code (e.g. "remote_error", "connection_failed") and `detail` is the
    surfaced upstream body (truncated to ~300 chars)."""
    success: bool
    elapsed_ms: int
    model: str
    endpoint: str
    code: Optional[str] = None
    detail: Optional[str] = None


def _make_synthetic_image_b64() -> str:
    """200×200 gradient JPEG, lazily generated.

    PIL is imported inside the function (not at module top) to avoid
    cold-start cost — most callers never use this fallback, they pass
    their own `image_b64`."""
    from PIL import Image

    img = Image.new("RGB", (200, 200))
    px = img.load()
    for y in range(200):
        for x in range(200):
            px[x, y] = (x % 256, y % 256, (x + y) % 256)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return base64.b64encode(buf.getvalue()).decode("ascii")


def probe_ollama_vlm(
    endpoint: str,
    model: str,
    *,
    image_b64: Optional[str] = None,
    prompt: str = _PROBE_PROMPT,
    max_tokens: int = 200,
) -> ProbeResult:
    """Send one VLM chat request to an Ollama-style endpoint and report.

    Forces the streaming path (abort_hook present) since that's what
    summary frame-picks actually use; proxy error frames behave the same
    on both paths but we match production flow so the probe surface stays
    representative.

    Args:
        endpoint: e.g. "http://192.168.9.160:11435" (no trailing slash).
        model: model name as the proxy expects it (LiteLLM `model_group`
            for *-vllm / *-ollama suffixed names).
        image_b64: optional caller-supplied base64; defaults to a 200×200
            synthetic JPEG so callers don't need to manage test fixtures.
        prompt: short text instruction sent with the image.
        max_tokens: caps response length; default 200 keeps probe latency
            bounded even when the upstream model is healthy.

    Returns:
        ProbeResult — see field docs.
    """
    from app.adapters.ai.remote.ollama import OllamaProvider
    from app.handler.exceptions import RemoteApiError

    b64 = image_b64 or _make_synthetic_image_b64()
    # Ollama-native shape: plain string content + sibling images list
    # (matches what `vision_messages.build_vision_chat_messages(
    # provider="ollama", ...)` emits in production).
    messages = [{
        "role": "user",
        "content": prompt,
        "images": [b64],
    }]

    prov = OllamaProvider(endpoint, None)
    start = time.monotonic()
    try:
        text = prov.chat(
            model=model,
            messages=messages,
            max_tokens=max_tokens,
            temperature=0.1,
            abort_hook=lambda r: None,
        )
        return ProbeResult(
            success=True,
            elapsed_ms=int((time.monotonic() - start) * 1000),
            model=model,
            endpoint=endpoint,
            detail=text[:300] if text else None,
        )
    except RemoteApiError as e:
        return ProbeResult(
            success=False,
            elapsed_ms=int((time.monotonic() - start) * 1000),
            model=model,
            endpoint=endpoint,
            code=e.code,
            detail=e.detail,
        )
    except Exception as e:
        # Catch-all so the probe contract holds — never raises. Includes
        # urllib errors not already wrapped by OllamaProvider (e.g. the
        # rare case where errors bubble out before _parse_error gets to
        # them) and PIL errors on synthetic image generation.
        return ProbeResult(
            success=False,
            elapsed_ms=int((time.monotonic() - start) * 1000),
            model=model,
            endpoint=endpoint,
            code="probe_exception",
            detail=f"{type(e).__name__}: {e}"[:300],
        )
