"""Pick a representative frame timestamp for a time window.

Strategy:
  - scene_detect returns 0 candidates → middle of window used as sole candidate
  - 1 candidate + no VLM → use it directly
  - any candidates + VLM (and temp_dir) → extract all, let VLM pick or reject
  - VLM returns -1 (or any negative) → caller renders item with no image (None)
  - no VLM (or no temp_dir) → scene change closest to window midpoint (always float)
  - VLM raises → fallback to midpoint-nearest (always float)
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable, Optional

from app.handler.exceptions import TaskCancelledError

from .parse import even_indices

logger = logging.getLogger(__name__)

# vlm_callback signature:
#   (context_text: str, frame_paths: list[Path]) -> int (index of chosen frame)
VLMCallback = Callable[[str, list[Path]], int]

# Max candidate frames fed to a single VLM call. Large narrative windows hold
# dozens of scene-change candidates; sending them all in one chat_with_images
# call blows past the 900s HTTP timeout. See spec 2026-05-22 §2.
MAX_VLM_CANDIDATES = 8


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
    candidate_max_edge: Optional[int] = None,
    max_candidates: int = MAX_VLM_CANDIDATES,
) -> Optional[float]:
    """Return a single representative timestamp for [window_start, window_end].

    Returns ``None`` when a VLM is supplied and judges that no candidate frame
    matches ``context_text`` (callback returned a negative index) — the caller
    then renders that item with no inline image.

    All non-None return paths are clamped to the video's decodable range via
    ``_clamp_ts`` (``duration``/``fps`` default to no-clamp sentinels).

    ``scenes``: a precomputed whole-video scene list. When provided, candidates
    are filtered in-memory (end-exclusive) instead of a per-window decode.
    ``None`` → legacy per-window ``detect_in_window``.

    VLM gate: when ``vlm_callback`` AND ``temp_dir`` are both provided, every
    item is routed through the VLM (a window with no scene candidate uses its
    midpoint as the sole candidate). Without a VLM the legacy heuristic is used
    and a float is always returned.

    ``max_candidates``: on the VLM path, the candidate list is subsampled
    (evenly spaced) to at most this many frames before extraction so a single
    ``chat_with_images`` call never processes dozens of images. Only affects
    the VLM path; the non-VLM heuristic always sees every candidate.
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
        candidates = [mid]

    use_vlm = vlm_callback is not None and temp_dir is not None

    if not use_vlm:
        if len(candidates) == 1:
            return _clamp_ts(candidates[0], duration, fps)
        return _clamp_ts(min(candidates, key=lambda t: abs(t - mid)), duration, fps)

    # VLM path: cap candidate count so one chat_with_images call never
    # processes dozens of images (a large narrative window otherwise blows
    # past the 900s HTTP timeout — see spec 2026-05-22 §2). even_indices is a
    # no-op when len(candidates) <= max_candidates.
    candidates = [candidates[i] for i in even_indices(len(candidates), max_candidates)]

    # VLM path: extract each candidate, ask VLM to choose one or reject all.
    temp_dir.mkdir(parents=True, exist_ok=True)
    frame_paths: list[Path] = []
    for i, t in enumerate(candidates):
        ct = _clamp_ts(t, duration, fps)
        p = temp_dir / f"candidate_{i:03d}.jpg"
        _ekw = dict(input_path=video_path, output_path=p, timestamp=ct)
        if candidate_max_edge is not None:
            _ekw["max_edge"] = candidate_max_edge
        detector.extract_frame(**_ekw)
        frame_paths.append(p)

    try:
        idx = vlm_callback(context_text, frame_paths)
        if idx < 0:
            logger.debug("VLM rejected all candidates; no frame for this item")
            return None
        idx = max(0, min(idx, len(candidates) - 1))
        return _clamp_ts(candidates[idx], duration, fps)
    except TaskCancelledError:
        raise
    except Exception as e:
        logger.warning(f"VLM pick failed: {e}; fallback to midpoint-nearest")
        return _clamp_ts(min(candidates, key=lambda t: abs(t - mid)), duration, fps)
