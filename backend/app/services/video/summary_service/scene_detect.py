"""PySceneDetect wrapper for detecting scene changes within time windows."""
from __future__ import annotations

import logging
from pathlib import Path

from app.adapters.binary.ffmpeg import FFmpegWrapper

logger = logging.getLogger(__name__)


class SceneDetector:
    """Detect scene change timestamps using PySceneDetect; extract frames via FFmpeg.

    PySceneDetect pulls in OpenCV at import time, so the ``scenedetect`` package
    is imported lazily inside ``detect_in_window`` to keep cold-start fast (per
    BACKEND_DEVELOP_SPEC §3.2).
    """

    def __init__(self, ffmpeg: FFmpegWrapper):
        self._ffmpeg = ffmpeg
        self._all_cache: dict[str, list[float]] = {}

    def detect_all(self, video_path: Path, threshold: float = 27.0) -> list[float]:
        """Return ALL scene-change start timestamps for the whole video.

        One full-video pass (no start/end), cached per path so callers can
        replace ~N per-window decodes with a single decode + in-memory filter.
        Same lazy-import + ``except → []`` contract as :meth:`detect_in_window`.
        """
        key = str(video_path)
        if key in self._all_cache:
            return self._all_cache[key]
        # Lazy import — scenedetect transitively loads cv2 which is heavy.
        import scenedetect
        from scenedetect import ContentDetector

        try:
            scenes = scenedetect.detect(
                str(video_path), ContentDetector(threshold=threshold)
            )
        except Exception as e:
            logger.warning(
                f"PySceneDetect detect_all failed on {video_path.name}: {e}"
            )
            self._all_cache[key] = []
            return []

        out = [s[0].get_seconds() for s in scenes]
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
