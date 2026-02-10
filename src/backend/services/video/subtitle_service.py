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
from backend.core.models.whisper import WhisperWrapper, get_whisper, TranscribeResult
from backend.core.models.translation import get_translator
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
        target_language: Optional[str] = None,
        translate_model_size: str = "4b",
        translate_model_type: str = "translategemma",
        translate_quantization: Optional[str] = None,
        # 進階分句參數
        word_timestamps: bool = False,
        condition_on_previous_text: bool = True,
        min_silence_duration_ms: int = 500,
        vad_threshold: float = 0.5,
        # 翻譯選項
        keep_names: bool = True,
        translate_style: str = "colloquial",
        glossary: Optional[dict[str, str]] = None,
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
            target_language: 翻譯目標語言 (None=不翻譯)
            translate_model_size: 翻譯模型大小 (4b, 12b, 27b)
            word_timestamps: 啟用詞級時間戳
            condition_on_previous_text: 是否根據前文調整辨識
            min_silence_duration_ms: 最小靜音時長（毫秒）
            vad_threshold: VAD 門檻值 (0-1)
            keep_names: 保留人名和專有名詞原文
            translate_style: 翻譯風格 (colloquial/formal/literal)

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
            "target_language": target_language,
            "translate_model_size": translate_model_size,
            "translate_model_type": translate_model_type,
            "translate_quantization": translate_quantization,
            "word_timestamps": word_timestamps,
            "condition_on_previous_text": condition_on_previous_text,
            "min_silence_duration_ms": min_silence_duration_ms,
            "vad_threshold": vad_threshold,
            "keep_names": keep_names,
            "translate_style": translate_style,
            "glossary": glossary,
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

        無翻譯流程:
        1. 用 FFmpeg 從影片提取音訊 (WAV 16kHz mono) — 進度 0~10%
        2. 用 faster-whisper 轉錄音訊 — 進度 10~90%
        3. 將 segments 寫成 SRT/VTT 字幕檔 — 進度 90~100%

        有翻譯流程:
        1. 用 FFmpeg 從影片提取音訊 — 進度 0~10%
        2. 用 faster-whisper 轉錄音訊 — 進度 10~70%
        3. 用 TranslateGemma 翻譯 — 進度 70~95%
        4. 將 segments 寫成 SRT/VTT 字幕檔 — 進度 95~100%
        """
        file_id = params["file_id"]
        file_info = self._file_service.get_file(file_id)

        if file_info is None:
            raise ValueError(f"File not found: {file_id}")

        language = params.get("language")  # None = auto detect
        model_size = params.get("model_size", "medium")
        output_format = params.get("output_format", "srt")
        target_language = params.get("target_language")  # None = 不翻譯
        translate_model_size = params.get("translate_model_size", "4b")
        translate_model_type = params.get("translate_model_type", "translategemma")
        translate_quantization = params.get("translate_quantization")

        # 進階分句參數
        word_timestamps = params.get("word_timestamps", False)
        condition_on_previous_text = params.get("condition_on_previous_text", True)
        min_silence_duration_ms = params.get("min_silence_duration_ms", 500)
        vad_threshold = params.get("vad_threshold", 0.5)

        # 翻譯選項
        keep_names = params.get("keep_names", True)
        translate_style = params.get("translate_style", "colloquial")
        glossary = params.get("glossary")

        has_translation = target_language is not None

        # === 階段 1: 提取音訊 (0~10%) ===
        progress_callback(0.0, "正在從影片提取音訊...")

        # 建立暫存音訊路徑
        temp_audio_path = self._file_service.upload_dir / f"temp_audio_{uuid4().hex[:8]}.wav"

        try:
            await self._extract_audio(file_info.file_path, temp_audio_path)
            progress_callback(0.10, "音訊提取完成，準備語音辨識...")

            # === 階段 2: 語音辨識 ===
            # 無翻譯: 10~90%, 有翻譯: 10~70%
            whisper_end = 0.70 if has_translation else 0.90
            whisper_range = whisper_end - 0.10

            def whisper_progress(percent: float, msg: str):
                overall = 0.10 + percent * whisper_range
                progress_callback(overall, msg)

            result = self._whisper.transcribe(
                audio_path=temp_audio_path,
                language=language,
                model_size=model_size,
                on_progress=whisper_progress,
                word_timestamps=word_timestamps,
                condition_on_previous_text=condition_on_previous_text,
                min_silence_duration_ms=min_silence_duration_ms,
                vad_threshold=vad_threshold,
            )

            # === 階段 3 (選用): 翻譯字幕 (70~95%) ===
            from backend.core.models.whisper import TranscribeSegment

            # 保存原始 segments（用於翻譯時輸出雙語字幕）
            original_segments = list(result.segments)

            if has_translation:
                progress_callback(whisper_end, "準備翻譯字幕...")

                translator = get_translator(translate_model_type)
                seg_dicts = [
                    {"start": s.start, "end": s.end, "text": s.text}
                    for s in result.segments
                ]

                def translate_progress(percent: float, msg: str):
                    overall = 0.70 + percent * 0.25
                    progress_callback(overall, msg)

                translated = translator.translate_segments(
                    seg_dicts,
                    source_lang=result.language,
                    target_lang=target_language,
                    model_size=translate_model_size,
                    quantization=translate_quantization,
                    on_progress=translate_progress,
                    keep_names=keep_names,
                    style=translate_style,
                    glossary=glossary,
                )

                result.segments = [
                    TranscribeSegment(s["start"], s["end"], s["text"])
                    for s in translated
                ]

            # === 最終階段: 寫入字幕檔 ===
            write_start = 0.95 if has_translation else 0.90
            progress_callback(write_start, "正在生成字幕檔...")

            # 決定基礎檔名
            custom_output_filename = params.get("output_filename")
            if custom_output_filename:
                base_name = Path(custom_output_filename).stem
            else:
                base_name = Path(file_info.original_filename).stem

            # 決定輸出目錄（優先自訂 > 來源目錄 > 預設 output）
            custom_output_dir = params.get("output_dir")
            if custom_output_dir:
                output_dir_path = Path(custom_output_dir)
            elif file_info.source_dir:
                output_dir_path = Path(file_info.source_dir)
            else:
                output_dir_path = self._file_service.output_dir
            output_dir_path.mkdir(parents=True, exist_ok=True)

            output_files = []

            if has_translation:
                # 有翻譯：輸出兩個檔案
                # 1. 原始語言字幕 (XXX.<source_lang>.srt)
                source_lang = result.language  # e.g. "ja", "en"
                source_filename = f"{base_name}.{source_lang}.{output_format}"
                source_path = output_dir_path / source_filename

                # 建立原始語言的 result（使用翻譯前的 segments）
                from backend.core.models.whisper import TranscribeResult
                original_result = TranscribeResult(
                    language=result.language,
                    language_probability=result.language_probability,
                    segments=original_segments,  # 翻譯前保存的
                    duration=result.duration,
                )

                if output_format == "vtt":
                    _write_vtt(original_result, source_path)
                else:
                    _write_srt(original_result, source_path)

                source_file_id = str(uuid4())
                source_info = self._file_service.register_output(
                    file_id=source_file_id,
                    file_path=source_path,
                    original_filename=file_info.original_filename,
                )
                output_files.append({
                    "file_id": source_file_id,
                    "filename": source_info.filename,
                    "size": source_info.file_size,
                    "language": source_lang,
                    "type": "source",
                })

                # 2. 翻譯後字幕 (XXX.<target_lang>.srt)
                target_filename = f"{base_name}.{target_language}.{output_format}"
                target_path = output_dir_path / target_filename

                if output_format == "vtt":
                    _write_vtt(result, target_path)
                else:
                    _write_srt(result, target_path)

                target_file_id = str(uuid4())
                target_info = self._file_service.register_output(
                    file_id=target_file_id,
                    file_path=target_path,
                    original_filename=file_info.original_filename,
                )
                output_files.append({
                    "file_id": target_file_id,
                    "filename": target_info.filename,
                    "size": target_info.file_size,
                    "language": target_language,
                    "type": "translated",
                })

                output_file_id = target_file_id  # 主要輸出為翻譯後的檔案
                output_filename = target_info.filename
                output_size = target_info.file_size
            else:
                # 無翻譯：輸出單一檔案 (XXX.srt)
                final_filename = f"{base_name}.{output_format}"
                output_path = output_dir_path / final_filename

                if output_format == "vtt":
                    _write_vtt(result, output_path)
                else:
                    _write_srt(result, output_path)

                output_file_id = str(uuid4())
                output_info = self._file_service.register_output(
                    file_id=output_file_id,
                    file_path=output_path,
                    original_filename=file_info.original_filename,
                )
                output_files.append({
                    "file_id": output_file_id,
                    "filename": output_info.filename,
                    "size": output_info.file_size,
                    "language": result.language,
                    "type": "source",
                })
                output_filename = output_info.filename
                output_size = output_info.file_size

            progress_callback(1.0, "字幕生成完成")

            return {
                "output_file_id": output_file_id,
                "output_filename": output_filename,
                "output_size": output_size,
                "output_files": output_files,
                "language": result.language,
                "language_probability": result.language_probability,
                "segment_count": len(result.segments),
                "duration": result.duration,
                "translated": has_translation,
                "target_language": target_language,
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
