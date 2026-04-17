"""Audio cut service."""
import logging
from pathlib import Path
from typing import Callable

from app.engine.ffmpeg import FFmpegWrapper
from app.services.files.file_service import FileService
from app.workers.task_manager import TaskManager

logger = logging.getLogger(__name__)

TASK_TYPE_AUDIO_CUT = "audio.cut"


class AudioCutService:
    """Audio trimming service using FFmpeg stream copy."""

    def __init__(self, ffmpeg: FFmpegWrapper, file_service: FileService, task_manager: TaskManager):
        self._ffmpeg = ffmpeg
        self._file_service = file_service
        self._task_manager = task_manager
        self._task_manager.register_handler(
            TASK_TYPE_AUDIO_CUT, self._handle_task,
            output_policy="history",
        )
        logger.info("AudioCutService initialized")

    async def submit_cut(
        self,
        file_id: str,
        start_time: str,
        end_time: str,
    ) -> str:
        file_info = self._file_service.require_file(file_id)
        params = {
            "file_id": file_id,
            "start_time": start_time,
            "end_time": end_time,
        }
        task_id = await self._task_manager.submit(TASK_TYPE_AUDIO_CUT, params)
        logger.info(f"Audio cut task submitted: {task_id}")
        return task_id

    def _handle_task(self, params: dict, progress_callback: Callable[[float, str], None]) -> dict:
        return self._execute(params, progress_callback)

    def _execute(self, params: dict, progress_callback: Callable[[float, str], None]) -> dict:
        file_id = params["file_id"]
        file_info = self._file_service.require_file(file_id)

        ext = Path(file_info.original_filename).suffix or ".mp3"
        output_file_id, output_path = self._file_service.create_output_path(
            original_filename=file_info.original_filename,
            suffix="_cut",
            ext=ext,
        )

        progress_callback(0.0, "task.progress.cut_starting")
        self._ffmpeg.cut_sync(
            input_path=file_info.file_path,
            output_path=output_path,
            start_time=params["start_time"],
            end_time=params["end_time"],
            stream_copy=True,
        )
        progress_callback(0.5, "task.progress.cut_processing")

        output_info = self._file_service.register_output(
            file_id=output_file_id, file_path=output_path, original_filename=file_info.original_filename
        )
        progress_callback(1.0, "task.progress.cut_complete")
        return {"output_file_id": output_file_id, "output_filename": output_info.filename}
