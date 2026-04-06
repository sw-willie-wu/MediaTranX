"""
音訊剪輯服務
"""
import asyncio
import logging
from pathlib import Path
from typing import Callable
from uuid import uuid4

from app.engine.ffmpeg import FFmpeg
from app.handler.exceptions import FFmpegError
from app.services.files.file_service import FileService
from app.workers.task_manager import TaskManager

logger = logging.getLogger(__name__)

TASK_TYPE_AUDIO_CUT = "audio.cut"


class AudioCutService:

    def __init__(self, ffmpeg: FFmpeg, file_service: FileService, task_manager: TaskManager):
        self._ffmpeg = ffmpeg
        self._file_service = file_service
        self._task_manager = task_manager
        self._task_manager.register_handler(TASK_TYPE_AUDIO_CUT, self._handle_task)
        logger.info("AudioCutService initialized")

    async def submit_cut(
        self,
        file_id: str,
        start_time: str,
        end_time: str,
    ) -> str:
        file_info = self._file_service.get_file(file_id)
        if file_info is None:
            raise ValueError(f"File not found: {file_id}")
        params = {"file_id": file_id, "start_time": start_time, "end_time": end_time}
        task_id = await self._task_manager.submit(TASK_TYPE_AUDIO_CUT, params)
        logger.info(f"Audio cut task submitted: {task_id}")
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
        final_filename = f"{original_stem}_cut_{output_file_id[:8]}{ext}"

        output_dir_path = self._file_service.output_dir
        output_dir_path.mkdir(parents=True, exist_ok=True)
        output_path = output_dir_path / final_filename

        cmd = [
            self._ffmpeg.ffmpeg_path,
            "-i", str(file_info.file_path),
            "-ss", params["start_time"],
            "-to", params["end_time"],
            "-acodec", "copy",
            "-y", str(output_path),
        ]

        progress_callback(0.0, "開始剪輯...")
        process = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        progress_callback(0.5, "剪輯中...")
        stdout, stderr = await process.communicate()
        if process.returncode != 0:
            raise FFmpegError(f"FFmpeg error: {stderr.decode()}")

        output_info = self._file_service.register_output(
            file_id=output_file_id, file_path=output_path, original_filename=file_info.original_filename
        )
        progress_callback(1.0, "剪輯完成")
        return {"output_file_id": output_file_id, "output_filename": output_info.filename}
