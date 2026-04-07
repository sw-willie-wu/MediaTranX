"""
音訊音量調整服務
"""
import asyncio
import logging
from pathlib import Path
from typing import Callable
from uuid import uuid4

from app.engine.ffmpeg import FFmpegWrapper
from app.services.files.file_service import FileService
from app.workers.task_manager import TaskManager

logger = logging.getLogger(__name__)

TASK_TYPE_AUDIO_VOLUME = "audio.volume"


class AudioVolumeService:

    def __init__(self, ffmpeg: FFmpegWrapper, file_service: FileService, task_manager: TaskManager):
        self._ffmpeg = ffmpeg
        self._file_service = file_service
        self._task_manager = task_manager
        self._task_manager.register_handler(TASK_TYPE_AUDIO_VOLUME, self._handle_task)
        logger.info("AudioVolumeService initialized")

    async def submit_volume(
        self,
        file_id: str,
        volume_db: float = 0.0,
        normalize: bool = False,
    ) -> str:
        file_info = self._file_service.get_file(file_id)
        if file_info is None:
            raise ValueError(f"File not found: {file_id}")
        params = {"file_id": file_id, "volume_db": volume_db, "normalize": normalize}
        task_id = await self._task_manager.submit(TASK_TYPE_AUDIO_VOLUME, params)
        logger.info(f"Audio volume task submitted: {task_id}")
        return task_id

    def _handle_task(self, params: dict, progress_callback: Callable[[float, str], None]) -> dict:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(self._execute(params, progress_callback))
        finally:
            loop.close()

    async def _execute(self, params: dict, progress_callback: Callable[[float, str], None]) -> dict:
        file_id = params["file_id"]
        file_info = self._file_service.get_file(file_id)
        if file_info is None:
            raise ValueError(f"File not found: {file_id}")

        output_file_id = str(uuid4())
        ext = Path(file_info.original_filename).suffix or ".mp3"
        original_stem = Path(file_info.original_filename).stem
        suffix = "normalized" if params["normalize"] else f"vol{params['volume_db']:+.0f}dB"
        final_filename = f"{original_stem}_{suffix}_{output_file_id[:8]}{ext}"

        output_dir_path = self._file_service.output_dir
        output_dir_path.mkdir(parents=True, exist_ok=True)
        output_path = output_dir_path / final_filename

        if params["normalize"]:
            af_filter = "loudnorm"
        else:
            db = params["volume_db"]
            af_filter = f"volume={db:+.1f}dB"

        progress_callback(0.0, "task.progress.volume_starting")
        await self._ffmpeg.adjust_volume(
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
