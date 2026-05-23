"""PySceneDetect wrapper for detecting scene changes within time windows."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable, Optional

from app.adapters.binary.ffmpeg import FFmpegWrapper
from app.handler.exceptions import TaskCancelledError

logger = logging.getLogger(__name__)

# scdet threshold, 0-100 percentage scale (FFmpeg scdet default 10.0).
# Calibrated value — see spec §13.7.
SCENE_THRESHOLD = 10.0
# Downscale width for scene analysis (px). See spec §13.7.
ANALYZE_W = 640

# ── perf tuning (separate from filter-algorithm knobs above) ─────────────
# Cap FFmpeg decoder threads so background detect (parallel with Whisper)
# does not starve Whisper. dav1d unbounded (`-threads 0` / nproc) heavily
# contends with Whisper on 4K AV1 (dev e2e: Whisper 720s vs ~177s clean).
# Implemented via `-threads N` before -i; dav1d wrapper translates to
# Dav1dSettings.n_threads. OS thread count is slightly above N (tile workers).
# See spec 2026-05-24-summary-threads-cap-and-progress.md.
DETECT_THREAD_CAP = 4


class SceneDetector:
    """Detect scene change timestamps; extract frames via FFmpeg.

    ``detect_all`` runs a single FFmpeg ``scdet`` pass (see spec §13).
    ``detect_in_window`` is the legacy per-window fallback and still uses
    PySceneDetect — ``scenedetect`` pulls in OpenCV at import time, so it is
    imported lazily inside that method to keep cold-start fast.
    """

    def __init__(self, ffmpeg: FFmpegWrapper):
        self._ffmpeg = ffmpeg
        self._all_cache: dict[str, list[float]] = {}

    def detect_all(
        self,
        video_path: Path,
        scene_threshold: float = SCENE_THRESHOLD,
        on_progress: Optional[Callable[[float], None]] = None,
    ) -> list[float]:
        """Return ALL scene-change start timestamps for the whole video.

        One full-video FFmpeg ``scdet`` pass (see :meth:`FFmpegWrapper.detect_scenes`),
        cached per path so callers can replace ~N per-window decodes with a single
        decode + in-memory filter.

        ``on_progress`` (a 0..1 decode fraction callback) is passed straight
        through to ``detect_scenes`` — it is NOT the service-layer
        ``progress_callback(pct, msg)``; the caller wraps that mapping itself.

        Best-effort: any failure is logged and yields ``[]`` (callers fall back
        to midpoint sampling). ``TaskCancelledError`` is re-raised — it must not
        be swallowed into ``[]``. See spec §13.
        """
        key = str(video_path)
        if key in self._all_cache:
            return self._all_cache[key]
        try:
            out = self._ffmpeg.detect_scenes_sync(
                video_path,
                scene_threshold=scene_threshold,
                analyze_w=ANALYZE_W,
                on_progress=on_progress,
                threads=DETECT_THREAD_CAP,
            )
        except TaskCancelledError:
            raise
        except Exception as e:
            logger.warning(
                f"FFmpeg detect_all failed on {video_path.name}: {e}"
            )
            self._all_cache[key] = []
            return []

        self._all_cache[key] = out
        return out

    def detect_in_window(
        self,
        video_path: Path,
        start_sec: float,
        end_sec: float,
        threshold: float = 27.0,
    ) -> list[float]:
        """Return scene-change start timestamps within [start_sec, end_sec].

        Returns an empty list when PySceneDetect fails (logged as a warning),
        so callers can fall back to a uniform-sampling strategy.
        """
        # Lazy import — scenedetect transitively loads cv2 which is heavy.
        import scenedetect
        from scenedetect import ContentDetector

        try:
            scenes = scenedetect.detect(
                str(video_path),
                ContentDetector(threshold=threshold),
                start_time=start_sec,
                end_time=end_sec,
            )
        except Exception as e:
            logger.warning(
                f"PySceneDetect failed on {video_path.name} "
                f"[{start_sec}-{end_sec}]: {e}"
            )
            return []

        return [s[0].get_seconds() for s in scenes]

    def extract_frame(self, input_path: Path, output_path: Path,
                       timestamp: float, max_edge: int | None = None) -> None:
        """Extract one JPEG frame at a given timestamp via FFmpeg.

        ``max_edge`` is forwarded only when set, so callers that don't pass it
        keep the exact 3-kwarg call contract (see test_scene_detect.py).
        """
        kwargs = dict(input_path=input_path, output_path=output_path,
                      timestamp=timestamp)
        if max_edge is not None:
            kwargs["max_edge"] = max_edge
        self._ffmpeg.extract_frame_sync(**kwargs)
