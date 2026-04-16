"""Pick a representative frame timestamp for a time window.

Strategy:
  - scene_detect returns 0 candidates → middle of window
  - 1 candidate → use it
  - 2+ candidates + vlm_callback → extract all, let VLM pick
  - 2+ candidates, no VLM (or VLM raises) → scene change closest to window midpoint
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable, Optional

logger = logging.getLogger(__name__)

# vlm_callback signature:
#   (context_text: str, frame_paths: list[Path]) -> int (index of chosen frame)
VLMCallback = Callable[[str, list[Path]], int]


def pick_frame_timestamp(
    detector,
    vlm_callback: Optional[VLMCallback],
    video_path: Path,
    window_start: float,
    window_end: float,
    context_text: str,
    temp_dir: Optional[Path] = None,
) -> float:
    """Return a single representative timestamp for [window_start, window_end]."""
    mid = (window_start + window_end) / 2

    candidates = detector.detect_in_window(video_path, window_start, window_end)

    if not candidates:
        logger.debug(
            f"No scenes in [{window_start}-{window_end}]; using middle {mid}"
        )
        return mid

    if len(candidates) == 1:
        return candidates[0]

    if vlm_callback is None or temp_dir is None:
        return min(candidates, key=lambda t: abs(t - mid))

    # VLM path: extract each candidate, ask VLM to choose
    temp_dir.mkdir(parents=True, exist_ok=True)
    frame_paths: list[Path] = []
    for i, t in enumerate(candidates):
        p = temp_dir / f"candidate_{i:03d}.jpg"
        detector.extract_frame(input_path=video_path, output_path=p, timestamp=t)
        frame_paths.append(p)

    try:
        idx = vlm_callback(context_text, frame_paths)
        idx = max(0, min(idx, len(candidates) - 1))
        return candidates[idx]
    except Exception as e:
        logger.warning(f"VLM pick failed: {e}; fallback to midpoint-nearest")
        return min(candidates, key=lambda t: abs(t - mid))
