"""Tile/stitch inference helper for PTH-family image super-resolution models.

Pure tensor helper — no registry, no DI, no model lifecycle knowledge.
Consumed by PthWrapper and its subclasses.
"""
from __future__ import annotations

import math
from typing import Callable, Optional

import torch


def tile_inference_run(
    model,
    img_tensor: torch.Tensor,
    scale: int,
    tile_size: int,
    tile_pad: int = 32,
    on_progress: Optional[Callable[[float, str], None]] = None,
) -> torch.Tensor:
    """Run tiled inference to avoid OOM on large images.

    Tiles are processed with `tile_pad` border overlap to hide seams; the
    padded overlap is cropped from the tile output before stitching.

    Args:
        model: Callable taking a (1, C, H, W) tensor and returning an upscaled tensor.
        img_tensor: Input tensor shape (1, C, H, W).
        scale: Expected scale factor (used as fallback if first tile output
            doesn't give a cleaner measurement).
        tile_size: Tile edge length (pixels) in input coordinate system.
        tile_pad: Tile border padding, shared with neighbors for seamless output.
        on_progress: Optional callback `(progress_0_to_1, i18n_key)`.

    Returns:
        Output tensor shape (1, C, H * actual_scale, W * actual_scale).
    """
    _, _, h, w = img_tensor.shape
    tiles_x = math.ceil(w / tile_size)
    tiles_y = math.ceil(h / tile_size)
    total = tiles_x * tiles_y

    output: Optional[torch.Tensor] = None
    actual_scale = scale

    for iy in range(tiles_y):
        for ix in range(tiles_x):
            x1, x2 = ix * tile_size, min((ix + 1) * tile_size, w)
            y1, y2 = iy * tile_size, min((iy + 1) * tile_size, h)
            x1p = max(x1 - tile_pad, 0)
            x2p = min(x2 + tile_pad, w)
            y1p = max(y1 - tile_pad, 0)
            y2p = min(y2 + tile_pad, h)

            tile = img_tensor[:, :, y1p:y2p, x1p:x2p]
            with torch.no_grad():
                tile_out = model(tile)

            if output is None:
                actual_scale = tile_out.shape[3] // (x2p - x1p)
                output = img_tensor.new_zeros(
                    (img_tensor.shape[0], img_tensor.shape[1],
                     h * actual_scale, w * actual_scale)
                )

            ox1 = (x1 - x1p) * actual_scale
            ox2 = ox1 + (x2 - x1) * actual_scale
            oy1 = (y1 - y1p) * actual_scale
            oy2 = oy1 + (y2 - y1) * actual_scale
            output[
                :, :, y1 * actual_scale:y2 * actual_scale,
                      x1 * actual_scale:x2 * actual_scale
            ] = tile_out[:, :, oy1:oy2, ox1:ox2]

            done = iy * tiles_x + ix + 1
            if on_progress:
                on_progress(done / total, f"task.progress.tile_inference|{done}|{total}")

    return output
