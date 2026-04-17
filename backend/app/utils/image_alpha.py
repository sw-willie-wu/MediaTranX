"""RGBA alpha-channel preservation helper for per-pixel image processing.

Used by image services that convert input → RGB for the actual transform (most
PIL/NumPy ops work on RGB), then need to re-apply the original alpha to the
output. Auto-resizes alpha when the transform changes image dimensions
(e.g. super-resolution).
"""
from __future__ import annotations

from typing import Callable

from PIL import Image


def preserve_alpha(
    img: Image.Image,
    process_fn: Callable[[Image.Image], Image.Image],
) -> Image.Image:
    """Apply `process_fn` to RGB view of img and restore alpha if the source had any.

    Args:
        img: input PIL Image (any mode).
        process_fn: callable that takes an RGB Image and returns a processed Image.
            The output may differ in size (alpha will be resized to match).

    Returns:
        Processed Image. RGBA if original had non-opaque alpha; RGB otherwise.
    """
    img_rgba = img.convert("RGBA")
    alpha = img_rgba.split()[3]
    has_alpha = alpha.getextrema()[0] < 255

    rgb_in = img_rgba.convert("RGB") if has_alpha else img.convert("RGB")
    result = process_fn(rgb_in)

    if not has_alpha:
        return result

    if result.size != img.size:
        alpha = alpha.resize(result.size, Image.LANCZOS)

    out = result.convert("RGBA")
    out.putalpha(alpha)
    return out
