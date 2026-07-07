"""
Video cut service — trim video by time range.
"""
import logging
from pathlib import Path
from typing import Callable, Optional

from app.adapters.binary.ffmpeg import (
    FFmpegWrapper,
    TranscodeProgress,
)
from app.services.files.file_service import FileService
from app.workers.task_manager import TaskManager

logger = logging.getLogger(__name__)

TASK_TYPE_VIDEO_CUT = "video.cut"


class VideoCutService:
    """Service for trimming video files by start/end time range."""

    def __init__(self, ffmpeg: FFmpegWrapper, file_service: FileService, task_manager: TaskManager):
        self._ffmpeg = ffmpeg
        self._file_service = file_service
        self._task_manager = task_manager

        self._task_manager.register_handler(
            TASK_TYPE_VIDEO_CUT,
            self._handle_task,
            output_policy="history",
        )

        logger.info("VideoCutService initialized")

    async def submit_cut(
        self,
        file_id: str,
        start_time: float,
        end_time: float,
        stream_copy: bool = True,
        suppress_results: bool = False,
    ) -> str:
        """Submit a video cut task."""
        file_info = self._file_service.require_file(file_id)

        params = {
            "file_id": file_id,
            "start_time": start_time,
            "end_time": end_time,
            "stream_copy": stream_copy,
        }

        task_id = await self._task_manager.submit(
            TASK_TYPE_VIDEO_CUT, params, suppress_results=suppress_results
        )
        logger.info(f"Cut task submitted: {task_id} for file {file_id}")
        return task_id

    def _handle_task(
        self,
        params: dict,
        progress_callback: Callable[[float, str], None]
    ) -> dict:
        """Handle cut task (runs in executor)."""
        return self._execute(params, progress_callback)

    def _execute(
        self,
        params: dict,
        progress_callback: Callable[[float, str], None]
    ) -> dict:
        """Execute video cut."""
        file_id = params["file_id"]
        file_info = self._file_service.require_file(file_id)

        start_time = params["start_time"]
        end_time = params["end_time"]
        stream_copy = params.get("stream_copy", True)

        # Build output path
        output_file_id, output_path = self._file_service.create_output_path(
            original_filename=file_info.original_filename,
            suffix="_cut",
        )

        def on_ffmpeg_progress(progress: TranscodeProgress):
            progress_callback(
                progress.percent / 100,
                f"task.progress.cutting_video|{progress.percent:.1f}|{progress.speed:.1f}"
            )

        progress_callback(0.0, "task.progress.cut_starting")

        self._ffmpeg.cut_sync(
            input_path=file_info.file_path,
            output_path=output_path,
            start_time=start_time,
            end_time=end_time,
            stream_copy=stream_copy,
            on_progress=on_ffmpeg_progress,
        )

        output_info = self._file_service.register_output(
            file_id=output_file_id,
            file_path=output_path,
            original_filename=file_info.original_filename,
        )

        progress_callback(1.0, "task.progress.cut_complete")

        return {
            "output_file_id": output_file_id,
            "output_filename": output_info.filename,
            "output_size": output_info.file_size,
        }
