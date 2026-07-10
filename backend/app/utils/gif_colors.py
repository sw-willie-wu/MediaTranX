"""Utility for counting distinct colors in a GIF image."""
from pathlib import Path
from PIL import Image, ImageSequence


def count_gif_colors(path, *, max_sample_pixels: int | None = None) -> int:
    """Distinct colors actually used across all frames of a (possibly animated) GIF, capped at 256.

    max_sample_pixels=None (default): exact full scan — original behavior, used by
    the compress task which needs the true count for its `gc < actual` decision.

    max_sample_pixels=<int>: approximate fast mode for the info path. Each frame is
    NEAREST-downscaled so the total sampled pixels stay within budget. NEAREST picks
    existing source pixels (never blends), so the sampled color set is a strict
    subset of the real one → the result can only underestimate, never overestimate.
    When total pixels <= budget no downscale happens and the result is exact.
    NEVER use an interpolating filter (BILINEAR/BICUBIC/LANCZOS) here — blending
    invents intermediate colors and would overestimate.

    Wall-time note: Pillow still DECODES every frame regardless of budget
    (LZW + disposal compositing), so there is a decode-bound floor
    (~0.8s for 17 frames of 2560x2240). The budget trims the color-union
    cost only: 6.2s full scan -> ~1.0s. Do not expect ms-level here.

    NOTE: PIL returns heterogeneous frame modes for animated GIFs (frame0='P', later frames 'RGB'
    due to disposal), so each frame MUST be convert('RGB')ed before unioning — do NOT union raw
    getdata() (mixes palette ints with RGB tuples → garbage).
    """
    colors: set = set()
    with Image.open(path) as im:
        per_frame_budget: int | None = None
        if max_sample_pixels is not None:
            n_frames = getattr(im, "n_frames", 1) or 1
            per_frame_budget = max(1, max_sample_pixels // n_frames)
        for frame in ImageSequence.Iterator(im):
            rgb = frame.convert("RGB")
            if per_frame_budget is not None and rgb.width * rgb.height > per_frame_budget:
                scale = (per_frame_budget / (rgb.width * rgb.height)) ** 0.5
                w = max(1, int(rgb.width * scale))
                h = max(1, int(rgb.height * scale))
                rgb = rgb.resize((w, h), Image.NEAREST)
            colors |= set(rgb.getdata())
            if len(colors) > 256:
                return 256
    return min(len(colors), 256)
