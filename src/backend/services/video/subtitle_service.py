"""
字幕提取服務
使用 faster-whisper 從影片中提取語音並生成字幕檔
"""
import asyncio
import logging
from pathlib import Path
from typing import Any, Callable, Optional
from uuid import uuid4

from backend.core.ffmpeg import FFmpeg, FFmpegError, get_ffmpeg
from backend.core.whisper import WhisperWrapper, get_whisper, TranscribeResult
from backend.services.file_service import FileService, get_file_service
from backend.workers.task_manager import TaskManager, get_task_manager

logger = logging.getLogger(__name__)

# 任務類型常數
TASK_TYPE_SUBTITLE_GENERATE = "video.subtitle_generate"


def _format_srt_time(seconds: float) -> str:
    """將秒數格式化為 SRT 時間格式 (HH:MM:SS,mmm)"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds % 1) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def _format_vtt_time(seconds: float) -> str:
    """將秒數格式化為 VTT 時間格式 (HH:MM:SS.mmm)"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds % 1) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}.{millis:03d}"


def _write_srt(result: TranscribeResult, output_path: Path) -> None:
    """將轉錄結果寫入 SRT 格式"""
    with open(output_path, "w", encoding="utf-8") as f:
        for i, seg in enumerate(result.segments, 1):
            f.write(f"{i}\n")
            f.write(f"{_format_srt_time(seg.start)} --> {_format_srt_time(seg.end)}\n")
            f.write(f"{seg.text}\n\n")


def _write_vtt(result: TranscribeResult, output_path: Path) -> None:
    """將轉錄結果寫入 VTT 格式"""
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("WEBVTT\n\n")
        for i, seg in enumerate(result.segments, 1):
            f.write(f"{i}\n")
            f.write(f"{_format_vtt_time(seg.start)} --> {_format_vtt_time(seg.end)}\n")
            f.write(f"{seg.text}\n\n")


class SubtitleService:
    """
    字幕提取服務
    整合 FFmpeg（提取音訊）、faster-whisper（語音辨識）和檔案管理
    """

    _instance: Optional["SubtitleService"] = None

    def __new__(cls, *args, **kwargs):
        """單例模式"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        self._ffmpeg: FFmpeg = get_ffmpeg()
        self._whisper: WhisperWrapper = get_whisper()
        self._file_service: FileService = get_file_service()
        self._task_manager: TaskManager = get_task_manager()

        # 註冊任務處理器
        self._task_manager.register_handler(
            TASK_TYPE_SUBTITLE_GENERATE,
            self._handle_subtitle_task
        )

        self._initialized = True
        logger.info("SubtitleService initialized")

    def get_model_status(self, model_size: str = "medium") -> dict:
        """查詢 Whisper 模型狀態"""
        return self._whisper.get_model_status(model_size)

    async def submit_subtitle_generate(
        self,
        file_id: str,
        language: Optional[str] = None,
        model_size: str = "medium",
        output_format: str = "srt",
        output_dir: Optional[str] = None,
        output_filename: Optional[str] = None,
    ) -> str:
        """
        提交字幕生成任務

        Args:
            file_id: 輸入影片檔案 ID
            language: 語言代碼 (None=自動偵測, "zh"=中文, "en"=英文...)
            model_size: 模型大小 (tiny, base, small, medium, large-v3)
            output_format: 輸出格式 (srt, vtt)
            output_dir: 自訂輸出目錄（可選）
            output_filename: 自訂輸出檔名（可選）

        Returns:
            task_id: 任務 ID
        """
        # 驗證檔案存在
        file_info = self._file_service.get_file(file_id)
        if file_info is None:
            raise ValueError(f"File not found: {file_id}")

        # 建立任務參數
        params = {
            "file_id": file_id,
            "language": language,
            "model_size": model_size,
            "output_format": output_format,
            "output_dir": output_dir,
            "output_filename": output_filename,
        }

        # 提交任務
        task_id = await self._task_manager.submit(TASK_TYPE_SUBTITLE_GENERATE, params)
        logger.info(f"Subtitle generate task submitted: {task_id} for file {file_id}")

        return task_id

    def _handle_subtitle_task(
        self,
        params: dict,
        progress_callback: Callable[[float, str], None]
    ) -> dict:
        """
        處理字幕生成任務（在 executor 中執行）
        """
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(
                self._execute_subtitle_generate(params, progress_callback)
            )
        finally:
            loop.close()

    async def _execute_subtitle_generate(
        self,
        params: dict,
        progress_callback: Callable[[float, str], None]
    ) -> dict:
        """
        執行字幕生成

        流程:
        1. 用 FFmpeg 從影片提取音訊 (WAV 16kHz mono) — 進度 0~10%
        2. 用 faster-whisper 轉錄音訊 — 進度 10~90%
        3. 將 segments 寫成 SRT/VTT 字幕檔 — 進度 90~100%
        """
        file_id = params["file_id"]
        file_info = self._file_service.get_file(file_id)

        if file_info is None:
            raise ValueError(f"File not found: {file_id}")

        language = params.get("language")  # None = auto detect
        model_size = params.get("model_size", "medium")
        output_format = params.get("output_format", "srt")

        # === 階段 1: 提取音訊 (0~10%) ===
        progress_callback(0.0, "正在從影片提取音訊...")

        # 建立暫存音訊路徑
        temp_audio_path = self._file_service.upload_dir / f"temp_audio_{uuid4().hex[:8]}.wav"

        try:
            await self._extract_audio(file_info.file_path, temp_audio_path)
            progress_callback(0.10, "音訊提取完成，準備語音辨識...")

            # === 階段 2: 語音辨識 (10~90%) ===
            def whisper_progress(percent: float, msg: str):
                # 將 whisper 的 0~1 映射到整體的 0.10~0.90
                overall = 0.10 + percent * 0.80
                progress_callback(overall, msg)

            result = self._whisper.transcribe(
                audio_path=temp_audio_path,
                language=language,
                model_size=model_size,
                on_progress=whisper_progress,
            )

            progress_callback(0.90, "正在生成字幕檔...")

            # === 階段 3: 寫入字幕檔 (90~100%) ===
            output_file_id = str(uuid4())

            # 決定檔名
            custom_output_filename = params.get("output_filename")
            if custom_output_filename:
                base_name = Path(custom_output_filename).stem
                final_filename = f"{base_name}.{output_format}"
            else:
                original_stem = Path(file_info.original_filename).stem
                final_filename = f"{original_stem}.{output_format}"

            # 決定輸出目錄（優先自訂 > 來源目錄 > 預設 output）
            custom_output_dir = params.get("output_dir")
            if custom_output_dir:
                output_dir_path = Path(custom_output_dir)
            elif file_info.source_dir:
                output_dir_path = Path(file_info.source_dir)
            else:
                output_dir_path = self._file_service.output_dir
            output_dir_path.mkdir(parents=True, exist_ok=True)
            output_path = output_dir_path / final_filename

            # 寫入字幕檔
            if output_format == "vtt":
                _write_vtt(result, output_path)
            else:
                _write_srt(result, output_path)

            # 註冊輸出檔案
            output_info = self._file_service.register_output(
                file_id=output_file_id,
                file_path=output_path,
                original_filename=file_info.original_filename,
            )

            progress_callback(1.0, "字幕生成完成")

            return {
                "output_file_id": output_file_id,
                "output_filename": output_info.filename,
                "output_size": output_info.file_size,
                "language": result.language,
                "language_probability": result.language_probability,
                "segment_count": len(result.segments),
                "duration": result.duration,
            }

        finally:
            # 清理暫存音訊檔
            if temp_audio_path.exists():
                try:
                    temp_audio_path.unlink()
                except OSError:
                    logger.warning(f"Failed to delete temp audio: {temp_audio_path}")

    async def _extract_audio(self, input_path: Path, output_path: Path) -> None:
        """
        用 FFmpeg 從影片中提取音訊為 WAV (16kHz, mono)

        faster-whisper 最佳輸入格式: 16kHz 單聲道 WAV
        """
        args = [
            self._ffmpeg.ffmpeg_path,
            "-y",
            "-i", str(input_path),
            "-vn",               # 不處理影片
            "-acodec", "pcm_s16le",  # 16-bit PCM
            "-ar", "16000",      # 16kHz
            "-ac", "1",          # 單聲道
            str(output_path),
        ]

        proc = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        _, stderr = await proc.communicate()

        if proc.returncode != 0:
            raise FFmpegError(f"音訊提取失敗: {stderr.decode()}")


# 全域服務實例
_subtitle_service: Optional[SubtitleService] = None


def get_subtitle_service() -> SubtitleService:
    """取得全域字幕服務實例"""
    global _subtitle_service
    if _subtitle_service is None:
        _subtitle_service = SubtitleService()
    return _subtitle_service
