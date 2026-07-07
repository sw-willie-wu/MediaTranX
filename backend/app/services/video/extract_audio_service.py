"""
Video extract-audio service — extract audio track from video files.
"""
import logging
from pathlib import Path
from typing import Callable, Optional

from app.adapters.binary.ffmpeg import (
    FFmpegWrapper,
    FFmpegError,
    TranscodeProgress,
)
from app.services.files.file_service import FileService
from app.workers.task_manager import TaskManager

logger = logging.getLogger(__name__)

TASK_TYPE_VIDEO_EXTRACT_AUDIO = "video.extract_audio"


class VideoExtractAudioService:
    """Service for extracting audio tracks from video files."""

    def __init__(self, ffmpeg: FFmpegWrapper, file_service: FileService, task_manager: TaskManager):
        self._ffmpeg = ffmpeg
        self._file_service = file_service
        self._task_manager = task_manager

        self._task_manager.register_handler(
            TASK_TYPE_VIDEO_EXTRACT_AUDIO,
            self._handle_task,
            output_policy="results",
        )

        logger.info("VideoExtractAudioService initialized")

    async def submit_extract_audio(
        self,
        file_id: str,
        audio_format: str = "mp3",
        audio_bitrate: Optional[str] = None,
        suppress_results: bool = False,
    ) -> str:
        """Submit an audio extraction task."""
        file_info = self._file_service.require_file(file_id)

        params = {
            "file_id": file_id,
            "audio_format": audio_format,
            "audio_bitrate": audio_bitrate,
        }

        task_id = await self._task_manager.submit(
            TASK_TYPE_VIDEO_EXTRACT_AUDIO, params, suppress_results=suppress_results
        )
        logger.info(f"Extract audio task submitted: {task_id} for file {file_id}")
        return task_id

    def _handle_task(
        self,
        params: dict,
        progress_callback: Callable[[float, str], None]
    ) -> dict:
        """Handle audio extraction task (runs in executor)."""
        return self._execute(params, progress_callback)

    def _execute(
        self,
        params: dict,
        progress_callback: Callable[[float, str], None]
    ) -> dict:
        """Execute audio extraction."""
        file_id = params["file_id"]
        file_info = self._file_service.require_file(file_id)

        audio_format = params.get("audio_format", "mp3")
        audio_bitrate = params.get("audio_bitrate")

        # Build output path
        output_file_id, output_path = self._file_service.create_output_path(
            original_filename=file_info.original_filename,
            suffix="_audio",
            ext=f".{audio_format}",
        )

        def on_ffmpeg_progress(progress: TranscodeProgress):
            progress_callback(
                progress.percent / 100,
                f"task.progress.extracting_audio|{progress.percent:.1f}|{progress.speed:.1f}"
            )

        progress_callback(0.0, "task.progress.extract_audio_starting")

        try:
            self._ffmpeg.extract_audio_sync(
                input_path=file_info.file_path,
                output_path=output_path,
                audio_format=audio_format,
                audio_bitrate=audio_bitrate,
                on_progress=on_ffmpeg_progress,
            )

            output_info = self._file_service.register_output(
                file_id=output_file_id,
                file_path=output_path,
                original_filename=file_info.original_filename,
            )

            progress_callback(1.0, "task.progress.extract_audio_complete")

            return {
                "output_file_id": output_file_id,
                "output_filename": output_info.filename,
                "output_size": output_info.file_size,
            }

        except FFmpegError as e:
            logger.error(f"Extract audio failed: {e}")
            raise
