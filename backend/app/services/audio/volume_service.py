"""Audio volume adjustment service."""
import logging
from pathlib import Path
from typing import Callable

from app.adapters.binary.ffmpeg import FFmpegWrapper
from app.services.files.file_service import FileService
from app.workers.task_manager import TaskManager

logger = logging.getLogger(__name__)

TASK_TYPE_AUDIO_VOLUME = "audio.volume"


class AudioVolumeService:
    """Audio volume adjustment and loudness normalization service."""

    def __init__(self, ffmpeg: FFmpegWrapper, file_service: FileService, task_manager: TaskManager):
        self._ffmpeg = ffmpeg
        self._file_service = file_service
        self._task_manager = task_manager
        self._task_manager.register_handler(
            TASK_TYPE_AUDIO_VOLUME, self._handle_task,
            output_policy="history",
        )
        logger.info("AudioVolumeService initialized")

    async def submit_volume(
        self,
        file_id: str,
        volume_db: float = 0.0,
        normalize: bool = False,
        suppress_results: bool = False,
    ) -> str:
        file_info = self._file_service.require_file(file_id)
        params = {"file_id": file_id, "volume_db": volume_db, "normalize": normalize}
        task_id = await self._task_manager.submit(
            TASK_TYPE_AUDIO_VOLUME, params, suppress_results=suppress_results
        )
        logger.info(f"Audio volume task submitted: {task_id}")
        return task_id

    def _handle_task(self, params: dict, progress_callback: Callable[[float, str], None]) -> dict:
        return self._execute(params, progress_callback)

    def _execute(self, params: dict, progress_callback: Callable[[float, str], None]) -> dict:
        file_id = params["file_id"]
        file_info = self._file_service.require_file(file_id)

        ext = Path(file_info.original_filename).suffix or ".mp3"
        suffix = "normalized" if params["normalize"] else f"vol{params['volume_db']:+.0f}dB"
        output_file_id, output_path = self._file_service.create_output_path(
            original_filename=file_info.original_filename,
            suffix=f"_{suffix}",
            ext=ext,
        )

        if params["normalize"]:
            af_filter = "loudnorm"
        else:
            db = params["volume_db"]
            af_filter = f"volume={db:+.1f}dB"

        progress_callback(0.0, "task.progress.volume_starting")
        self._ffmpeg.adjust_volume_sync(
            input_path=file_info.file_path,
            output_path=output_path,
            af_filter=af_filter,
        )
        progress_callback(0.5, "task.progress.volume_processing")

        output_info = self._file_service.register_output(
            file_id=output_file_id, file_path=output_path, original_filename=file_info.original_filename
        )
        progress_callback(1.0, "task.progress.volume_complete")
        return {"output_file_id": output_file_id, "output_filename": output_info.filename}
