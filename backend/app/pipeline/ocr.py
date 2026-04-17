"""Cross-service VLM single-image OCR orchestration.

Currently exposes the **local** recognition flow only. Remote-provider VLM OCR
is divergent between `image/ocr_service` (full: resize / compress / 3-way
provider message format) and `document/doc_ocr_service` (minimal: openai-compat
only). Wave 3 §6.2 #7/#8 (shared vision-message assembly + bug fixes for
ollama/gemini + resize) will consolidate that.
"""
from __future__ import annotations

import logging
import os
import tempfile
from pathlib import Path
from typing import Callable, Optional

logger = logging.getLogger(__name__)


def recognize_image_local(
    image_path: str,
    model_family: str,
    variant: str,
    fmt: str,
    runtime,
    on_progress: Optional[Callable[[float, str], None]] = None,
) -> str:
    """Single-image VLM OCR via local llama-server runtime.

    Caller owns `runtime.acquire()` — this function does NOT acquire. It assumes
    the runtime is already holding the requested model.

    Args:
        image_path: absolute path to the image
        model_family: e.g. "qwen3vl", "internvl2.5", "gemma4"
        variant: model variant used for inference_config lookup; may be "4b" or "4b:Q4_K_M"
        fmt: output format, "md" or "txt"
        runtime: acquired LlamaServerRuntime instance
        on_progress: optional 0..1 progress callback; fake_progress interpolates while chat runs.

    Returns:
        Extracted text as a string (possibly empty).
    """
    from app.utils.inference import get_inference_config, calc_max_tokens, fake_progress
    from app.utils.prompts import get_prompt_builder

    variant_size = variant.split(":")[0] if ":" in variant else variant
    config = get_inference_config(model_family, variant_size, "ocr")
    builder = get_prompt_builder("ocr", config["prompt_builder"], thinking=config.get("thinking", False))
    result = builder(image_path, output_format=fmt, source_lang=None)
    max_tokens = calc_max_tokens(config, config["n_ctx"], 1000)  # ~1000 tokens for image

    with fake_progress(on_progress, 0.0, 1.0, "task.progress.ocr_recognizing", runtime=runtime):
        return runtime.chat(
            messages=result["messages"], max_tokens=max_tokens,
            temperature=config["temperature"],
            top_k=config.get("top_k", 40), top_p=config.get("top_p", 0.9),
        )


def ocr_pdf_pages(
    pdf_path: str | Path,
    recognize_fn: Callable[[str], str],
    on_progress: Optional[Callable[[float, str], None]] = None,
    scale: float = 2.0,
) -> list[str]:
    """Render each PDF page to PNG and call `recognize_fn(png_path)` on each.

    Progress (when provided) spans 0..1 across all pages (caller remaps to their
    task range). Rendered PNGs live in a temp directory and are cleaned up on exit.
    Returns the list of `.strip()`-ed per-page results; caller composes them.
    """
    import pypdfium2 as pdfium

    pdf = pdfium.PdfDocument(str(pdf_path))
    total = len(pdf)
    results: list[str] = []

    try:
        with tempfile.TemporaryDirectory(prefix="mediatranx_ocr_") as tmpdir:
            for i in range(total):
                if on_progress:
                    on_progress(i / total, f"task.progress.doc_ocr_page|{i + 1}|{total}")
                page = pdf[i]
                bitmap = page.render(scale=scale)
                pil_image = bitmap.to_pil()
                img_path = os.path.join(tmpdir, f"page_{i}.png")
                pil_image.save(img_path)
                results.append(recognize_fn(img_path).strip())
    finally:
        pdf.close()

    return results
