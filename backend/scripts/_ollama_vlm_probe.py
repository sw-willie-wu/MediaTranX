"""CLI wrapper around app.adapters.ai.remote.probe.probe_ollama_vlm.

Use when the LAN proxy / Ollama endpoint mysteriously 500s and you need
to see what the upstream actually said. Surfaces detail via the fix in
fix/ollama-proxy-error-surface-detail (proxy `detail` field no longer
swallowed by `or`).

Usage:
  uv run python scripts/_ollama_vlm_probe.py
  uv run python scripts/_ollama_vlm_probe.py --endpoint http://x:11435 \\
      --models qwen3.5-122b-vllm,qwen3-vl:latest \\
      --image path/to/img.jpg \\
      --prompt "What is in this image?"
"""
from __future__ import annotations

import argparse
import logging
import os
import sys

# sys.path bootstrap (same pattern as other scripts/)
_BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)


def _load_image_b64(path: str) -> str:
    import base64
    from pathlib import Path
    return base64.b64encode(Path(path).read_bytes()).decode("ascii")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--endpoint",
        default=os.environ.get("MTX_OLLAMA_ENDPOINT", "http://192.168.9.160:11435"),
    )
    parser.add_argument(
        "--models",
        default="qwen3.5-122b-vllm,qwen3-vl:latest,llama3.2-vision:latest",
        help="comma-separated VLM model names to probe in order",
    )
    parser.add_argument("--image", default=None, help="path to a real image file")
    parser.add_argument("--prompt", default="Describe this image briefly.")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    image_b64 = _load_image_b64(args.image) if args.image else None
    if args.image:
        print(f"image: {args.image} ({len(image_b64)} b64 chars)")
    else:
        print("image: synthetic 200x200 gradient JPEG (auto-generated)")
    print(f"endpoint: {args.endpoint}")

    from app.adapters.ai.remote.probe import probe_ollama_vlm

    for model in [m.strip() for m in args.models.split(",") if m.strip()]:
        print(f"\n--- probing model={model} ---", flush=True)
        result = probe_ollama_vlm(
            args.endpoint, model,
            image_b64=image_b64, prompt=args.prompt,
        )
        if result.success:
            print(f"  [OK] {result.elapsed_ms}ms: {result.detail!r}")
        else:
            print(f"  [FAIL] {result.elapsed_ms}ms code={result.code!r}")
            print(f"    detail: {result.detail}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
