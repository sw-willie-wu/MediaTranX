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

from app.handler.exceptions import TaskCancelledError

logger = logging.getLogger(__name__)

# vlm_callback signature:
#   (context_text: str, frame_paths: list[Path]) -> int (index of chosen frame)
VLMCallback = Callable[[str, list[Path]], int]


def _clamp_ts(t: float, duration: Optional[float], fps: Optional[float]) -> float:
    """Clamp a timestamp into the decodable range of the video.

    LLM-generated time ranges can drift past the real video duration; an
    out-of-range ``-ss`` seek decodes zero frames and ffmpeg hard-fails. This
    keeps the timestamp inside ``[0, duration - margin]`` so a representative
    frame is still decodable.

    ``duration`` None or <= 0 (unknown / unprobeable container) → clamping
    disabled, only floor at 0; the caller's per-item try/except is the actual
    guarantee. ``margin`` keeps headroom for the last decodable frame
    (>= one frame interval, min 0.05s).
    """
    if duration is None or duration <= 0:
        return max(0.0, t)
    margin = max(0.05, (1.5 / fps) if fps else 0.05)
    return min(max(0.0, t), max(0.0, duration - margin))


def pick_frame_timestamp(
    detector,
    vlm_callback: Optional[VLMCallback],
    video_path: Path,
    window_start: float,
    window_end: float,
    context_text: str,
    temp_dir: Optional[Path] = None,
    duration: Optional[float] = None,
    fps: Optional[float] = None,
    scenes: Optional[list[float]] = None,
) -> float:
    """Return a single representative timestamp for [window_start, window_end].

    All return paths are clamped to the video's decodable range via
    ``_clamp_ts`` (``duration``/``fps`` default to no-clamp sentinels).

    ``scenes``: a precomputed whole-video scene list. When provided, candidates
    are filtered in-memory (end-exclusive, matching scenedetect ``end_time``
    semantics) instead of running a per-window decode — an empty filtered
    result takes the same midpoint path as no-candidate. ``None`` → legacy
    per-window ``detect_in_window`` (unchanged).
    """
    mid = (window_start + window_end) / 2

    if scenes is not None:
        candidates = [t for t in scenes if window_start <= t < window_end]
    else:
        candidates = detector.detect_in_window(video_path, window_start, window_end)

    if not candidates:
        logger.debug(
            f"No scenes in [{window_start}-{window_end}]; using middle {mid}"
        )
        return _clamp_ts(mid, duration, fps)

    if len(candidates) == 1:
        return _clamp_ts(candidates[0], duration, fps)

    if vlm_callback is None or temp_dir is None:
        return _clamp_ts(min(candidates, key=lambda t: abs(t - mid)), duration, fps)

    # VLM path: extract each candidate, ask VLM to choose
    temp_dir.mkdir(parents=True, exist_ok=True)
    frame_paths: list[Path] = []
    for i, t in enumerate(candidates):
        ct = _clamp_ts(t, duration, fps)
        p = temp_dir / f"candidate_{i:03d}.jpg"
        detector.extract_frame(input_path=video_path, output_path=p, timestamp=ct)
        frame_paths.append(p)

    try:
        idx = vlm_callback(context_text, frame_paths)
        idx = max(0, min(idx, len(candidates) - 1))
        return _clamp_ts(candidates[idx], duration, fps)
    except TaskCancelledError:
        raise
    except Exception as e:
        logger.warning(f"VLM pick failed: {e}; fallback to midpoint-nearest")
        return _clamp_ts(min(candidates, key=lambda t: abs(t - mid)), duration, fps)
