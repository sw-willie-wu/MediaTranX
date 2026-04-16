"""PySceneDetect wrapper for detecting scene changes within time windows."""
from __future__ import annotations

import logging
from pathlib import Path

from app.engine.ffmpeg import FFmpegWrapper

logger = logging.getLogger(__name__)


class SceneDetector:
    """Detect scene change timestamps using PySceneDetect; extract frames via FFmpeg.

    PySceneDetect pulls in OpenCV at import time, so the ``scenedetect`` package
    is imported lazily inside ``detect_in_window`` to keep cold-start fast (per
    BACKEND_DEVELOP_SPEC §3.2).
    """

    def __init__(self, ffmpeg: FFmpegWrapper | None = None):
        self._ffmpeg = ffmpeg or FFmpegWrapper()

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

    def extract_frame(self, input_path: Path, output_path: Path, timestamp: float) -> None:
        """Extract one JPEG frame at a given timestamp via FFmpeg."""
        self._ffmpeg.extract_frame_sync(
            input_path=input_path,
            output_path=output_path,
            timestamp=timestamp,
        )
