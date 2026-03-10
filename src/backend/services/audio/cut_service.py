"""
音訊剪輯服務
"""
import asyncio
import logging
from pathlib import Path
from typing import Callable, Optional
from uuid import uuid4

from backend.core.ffmpeg import FFmpeg, FFmpegError, get_ffmpeg
from backend.services.files.file_service import FileService, get_file_service
from backend.workers.task_manager import TaskManager, get_task_manager

logger = logging.getLogger(__name__)

TASK_TYPE_AUDIO_CUT = "audio.cut"


class AudioCutService:
    _instance: Optional["AudioCutService"] = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._ffmpeg: FFmpeg = get_ffmpeg()
        self._file_service: FileService = get_file_service()
        self._task_manager: TaskManager = get_task_manager()
        self._task_manager.register_handler(TASK_TYPE_AUDIO_CUT, self._handle_task)
        self._initialized = True
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

        output_dir_path = Path(file_info.source_dir) if file_info.source_dir else self._file_service.output_dir
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


_service: Optional[AudioCutService] = None

def get_audio_cut_service() -> AudioCutService:
    global _service
    if _service is None:
        _service = AudioCutService()
    return _service
