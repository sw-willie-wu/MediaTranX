"""Ad-hoc real-AI smoke: OllamaProvider.chat_with_images() against a
running Ollama instance.

Usage:
    uv run --project core/backend python core/backend/scripts/_remote_ollama_vision_smoke.py [image.png]

Environment:
    MTX_OLLAMA_ENDPOINT (default: http://localhost:11434)
    MTX_REMOTE_VLM_MODEL (default: qwen3.5:122b)

Prereqs:
- Ollama running with the chosen vision-capable model pulled
- An image file (default: synthesize a 320x240 PNG via Pillow)

Spec: Testing §Real-AI smoke.
"""
from __future__ import annotations
import os
import sys
import time
from pathlib import Path


def _make_test_image() -> Path:
    """Create a tiny test image. Uses Pillow which is already a backend dep."""
    from PIL import Image
    import tempfile

    img = Image.new("RGB", (320, 240), color=(20, 60, 120))
    f = Path(tempfile.mkstemp(suffix=".png")[1])
    img.save(f, "PNG")
    return f


def main() -> int:
    from app.adapters.ai.remote.ollama import OllamaProvider

    endpoint = os.environ.get("MTX_OLLAMA_ENDPOINT", "http://localhost:11434")
    model = os.environ.get("MTX_REMOTE_VLM_MODEL", "qwen3.5:122b")
    print(f"[setup] endpoint={endpoint} model={model}")

    if len(sys.argv) > 1:
        img_path = Path(sys.argv[1])
    else:
        img_path = _make_test_image()
        print(f"[setup] using synthesized test image: {img_path}")

    prov = OllamaProvider(endpoint, None)
    t0 = time.monotonic()
    result = prov.chat_with_images(
        model=model,
        prompt="Describe this image in one short sentence.",
        images=[img_path],
        max_tokens=200, temperature=0.0,
        abort_hook=lambda r: None,
    )
    dt = time.monotonic() - t0
    print(f"[chat_with_images] elapsed={dt:.2f}s len={len(result)} reply={result!r}")
    if not result.strip():
        print("FAIL: empty response", file=sys.stderr)
        return 1
    print("PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
