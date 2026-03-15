"""
音訊逐字稿轉譯服務
使用 faster-whisper 將音訊轉為文字
"""
import asyncio
import logging
from pathlib import Path
from typing import Callable, Optional
from uuid import uuid4

from app.engine.ai.bin.whisper import WhisperWrapper, get_whisper, TranscribeResult
from app.services.files.file_service import FileService, get_file_service
from app.workers.task_manager import TaskManager, get_task_manager

logger = logging.getLogger(__name__)

TASK_TYPE_AUDIO_TRANSCRIBE = "audio.transcribe"


def _format_srt_time(seconds: float) -> str:
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds % 1) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def _write_txt(result: TranscribeResult, output_path: Path) -> None:
    with open(output_path, "w", encoding="utf-8") as f:
        for seg in result.segments:
            f.write(seg.text.strip() + "\n")


def _write_srt(result: TranscribeResult, output_path: Path) -> None:
    with open(output_path, "w", encoding="utf-8") as f:
        for i, seg in enumerate(result.segments, 1):
            f.write(f"{i}\n")
            f.write(f"{_format_srt_time(seg.start)} --> {_format_srt_time(seg.end)}\n")
            f.write(f"{seg.text.strip()}\n\n")


class AudioTranscribeService:
    _instance: Optional["AudioTranscribeService"] = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._whisper: WhisperWrapper = get_whisper()
        self._file_service: FileService = get_file_service()
        self._task_manager: TaskManager = get_task_manager()
        self._task_manager.register_handler(TASK_TYPE_AUDIO_TRANSCRIBE, self._handle_task)
        self._initialized = True
        logger.info("AudioTranscribeService initialized")

    def get_model_status(self, model_size: str = "medium") -> dict:
        return self._whisper.get_model_status(model_size)

    async def submit_transcribe(
        self,
        file_id: str,
        language: Optional[str] = None,
        model_size: str = "medium",
        output_format: str = "txt",
    ) -> str:
        file_info = self._file_service.get_file(file_id)
        if file_info is None:
            raise ValueError(f"File not found: {file_id}")
        params = {
            "file_id": file_id,
            "language": language,
            "model_size": model_size,
            "output_format": output_format,
        }
        task_id = await self._task_manager.submit(TASK_TYPE_AUDIO_TRANSCRIBE, params)
        logger.info(f"Audio transcribe task submitted: {task_id}")
        return task_id

    def _handle_task(self, params: dict, progress_callback: Callable[[float, str], None]) -> dict:
        file_id = params["file_id"]
        file_info = self._file_service.get_file(file_id)
        if file_info is None:
            raise ValueError(f"File not found: {file_id}")

        output_format = params.get("output_format", "txt")
        output_file_id = str(uuid4())
        original_stem = Path(file_info.original_filename).stem
        final_filename = f"{original_stem}_transcript_{output_file_id[:8]}.{output_format}"

        output_dir_path = Path(file_info.source_dir) if file_info.source_dir else self._file_service.output_dir
        output_dir_path.mkdir(parents=True, exist_ok=True)
        output_path = output_dir_path / final_filename

        progress_callback(0.0, "載入模型...")

        result = self._whisper.transcribe(
            audio_path=str(file_info.file_path),
            language=params.get("language"),
            model_size=params.get("model_size", "medium"),
            word_timestamps=False,
            condition_on_previous_text=True,
            progress_callback=lambda p, m: progress_callback(p * 0.9, m),
        )

        progress_callback(0.9, "寫入檔案...")

        if output_format == "srt":
            _write_srt(result, output_path)
        else:
            _write_txt(result, output_path)

        output_info = self._file_service.register_output(
            file_id=output_file_id, file_path=output_path, original_filename=file_info.original_filename
        )
        progress_callback(1.0, "轉譯完成")
        return {
            "output_file_id": output_file_id,
            "output_filename": output_info.filename,
            "detected_language": result.language,
        }


_service: Optional[AudioTranscribeService] = None

def get_audio_transcribe_service() -> AudioTranscribeService:
    global _service
    if _service is None:
        _service = AudioTranscribeService()
    return _service
