"""
文件翻譯服務
使用 TranslateGemma 翻譯上傳的文字檔
支援純文字檔及字幕檔（SRT、VTT）
"""
import asyncio
import logging
import re
from pathlib import Path
from typing import Callable, Optional
from uuid import uuid4

from app.utils.prompts import (
    WHISPER_TO_BCP47,
    TranslateResult,
    build_translate_prompt,
    build_srt_translate_prompt,
    build_translate_messages,
    segments_to_srt,
    parse_srt_response,
    split_text,
)
from app.services.files.file_service import FileService
from app.workers.task_manager import TaskManager

logger = logging.getLogger(__name__)

# 任務類型常數
TASK_TYPE_DOCUMENT_TRANSLATE = "document.translate"

# 字幕檔副檔名
SUBTITLE_EXTENSIONS = {".srt", ".vtt"}


def _parse_srt_time(time_str: str) -> float:
    """解析 SRT 時間格式 (HH:MM:SS,mmm) 為秒數"""
    m = re.match(r"(\d+):(\d+):(\d+)[,.](\d+)", time_str.strip())
    if not m:
        return 0.0
    h, mi, s, ms = int(m[1]), int(m[2]), int(m[3]), int(m[4])
    return h * 3600 + mi * 60 + s + ms / 1000


def _format_srt_time(seconds: float) -> str:
    """將秒數格式化為 SRT 時間格式 (HH:MM:SS,mmm)"""
    h = int(seconds // 3600)
    mi = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int((seconds % 1) * 1000)
    return f"{h:02d}:{mi:02d}:{s:02d},{ms:03d}"


def _format_vtt_time(seconds: float) -> str:
    """將秒數格式化為 VTT 時間格式 (HH:MM:SS.mmm)"""
    h = int(seconds // 3600)
    mi = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int((seconds % 1) * 1000)
    return f"{h:02d}:{mi:02d}:{s:02d}.{ms:03d}"


def _parse_srt(text: str) -> list[dict]:
    """
    解析 SRT 字幕檔為 segments

    Returns:
        [{"start": float, "end": float, "text": str}, ...]
    """
    segments = []
    blocks = re.split(r"\n\s*\n", text.strip())
    for block in blocks:
        lines = block.strip().split("\n")
        if len(lines) < 2:
            continue
        # 找到時間軸行（包含 -->）
        time_line_idx = None
        for i, line in enumerate(lines):
            if "-->" in line:
                time_line_idx = i
                break
        if time_line_idx is None:
            continue
        parts = lines[time_line_idx].split("-->")
        if len(parts) != 2:
            continue
        start = _parse_srt_time(parts[0])
        end = _parse_srt_time(parts[1])
        content = "\n".join(lines[time_line_idx + 1:]).strip()
        if content:
            segments.append({"start": start, "end": end, "text": content})
    return segments


def _parse_vtt(text: str) -> list[dict]:
    """
    解析 VTT 字幕檔為 segments

    Returns:
        [{"start": float, "end": float, "text": str}, ...]
    """
    # 移除 WEBVTT 標頭及可能的 metadata
    body = re.sub(r"^WEBVTT[^\n]*\n", "", text.strip(), count=1).strip()
    # VTT 的時間格式用 . 而非 ,，但 _parse_srt_time 已經支援兩者
    return _parse_srt(body)


def _write_srt(segments: list[dict], output_path: Path) -> None:
    """將 segments 寫入 SRT 格式"""
    with open(output_path, "w", encoding="utf-8") as f:
        for i, seg in enumerate(segments, 1):
            f.write(f"{i}\n")
            f.write(f"{_format_srt_time(seg['start'])} --> {_format_srt_time(seg['end'])}\n")
            f.write(f"{seg['text']}\n\n")


def _write_vtt(segments: list[dict], output_path: Path) -> None:
    """將 segments 寫入 VTT 格式"""
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("WEBVTT\n\n")
        for i, seg in enumerate(segments, 1):
            f.write(f"{i}\n")
            f.write(f"{_format_vtt_time(seg['start'])} --> {_format_vtt_time(seg['end'])}\n")
            f.write(f"{seg['text']}\n\n")


class TranslateService:
    """
    文件翻譯服務
    整合 TranslateGemma 和檔案管理
    """

    def __init__(self, file_service: FileService, task_manager: TaskManager):
        self._file_service = file_service
        self._task_manager = task_manager

        # 註冊任務處理器
        self._task_manager.register_handler(
            TASK_TYPE_DOCUMENT_TRANSLATE,
            self._handle_translate_task,
        )

        logger.info("TranslateService initialized")

    async def submit_translate(
        self,
        file_id: str,
        source_language: str,
        target_language: str,
        model_size: str = "4b",
        model_type: str = "translategemma",
        quantization: Optional[str] = None,
        translate_style: str = "colloquial",
        glossary: Optional[dict[str, str]] = None,
        output_dir: Optional[str] = None,
        output_filename: Optional[str] = None,
    ) -> str:
        """
        提交文件翻譯任務

        Args:
            file_id: 輸入檔案 ID
            source_language: 來源語言
            target_language: 目標語言
            model_size: 模型大小 (4b, 12b, 27b)
            output_dir: 自訂輸出目錄
            output_filename: 自訂輸出檔名

        Returns:
            task_id
        """
        file_info = self._file_service.get_file(file_id)
        if file_info is None:
            raise ValueError(f"File not found: {file_id}")

        params = {
            "file_id": file_id,
            "source_language": source_language,
            "target_language": target_language,
            "model_size": model_size,
            "model_type": model_type,
            "quantization": quantization,
            "translate_style": translate_style,
            "glossary": glossary,
            "output_dir": output_dir,
            "output_filename": output_filename,
        }

        task_id = await self._task_manager.submit(TASK_TYPE_DOCUMENT_TRANSLATE, params)
        logger.info(f"Document translate task submitted: {task_id} for file {file_id}")

        return task_id

    def _handle_translate_task(
        self,
        params: dict,
        progress_callback: Callable[[float, str], None]
    ) -> dict:
        """處理翻譯任務（在 executor 中執行）"""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(
                self._execute_translate(params, progress_callback)
            )
        finally:
            loop.close()

    async def _execute_translate(
        self,
        params: dict,
        progress_callback: Callable[[float, str], None]
    ) -> dict:
        """
        執行文件翻譯

        流程:
        1. 讀取檔案 (0~5%)
        2. 翻譯 (5~95%)
        3. 寫入輸出檔 (95~100%)
        """
        file_id = params["file_id"]
        file_info = self._file_service.get_file(file_id)

        if file_info is None:
            raise ValueError(f"File not found: {file_id}")

        source_language = params["source_language"]
        target_language = params["target_language"]
        model_size = params.get("model_size", "4b")
        model_type = params.get("model_type", "translategemma")
        quantization = params.get("quantization")
        translate_style = params.get("translate_style", "colloquial")
        glossary = params.get("glossary")

        # === 階段 1: 讀取檔案 (0~5%) ===
        progress_callback(0.0, "task.progress.reading_file")

        file_path = Path(file_info.file_path)
        text = file_path.read_text(encoding="utf-8")
        ext = Path(file_info.original_filename).suffix.lower()
        is_subtitle = ext in SUBTITLE_EXTENSIONS

        progress_callback(0.05, f"task.progress.file_read_complete|{len(text)}")

        # === 階段 2: 翻譯 (5~95%) ===
        def translate_progress(percent: float, msg: str):
            overall = 0.05 + percent * 0.90
            progress_callback(overall, msg)

        is_remote = params.get("remote", False)

        if is_remote:
            # === 雲端翻譯 ===
            from app.utils.translate import get_cloud_provider, translate_srt_cloud, translate_text_cloud

            provider = params.get("provider", "")
            conn_id = params.get("conn_id")
            remote_model = params.get("remote_model", "")
            prov = get_cloud_provider(provider, conn_id, remote_model)

            if is_subtitle:
                if ext == ".vtt":
                    segments = _parse_vtt(text)
                else:
                    segments = _parse_srt(text)

                logger.info(f"Parsed {len(segments)} subtitle segments from {ext} file")
                src = WHISPER_TO_BCP47.get(source_language, source_language)

                translated_segments = translate_srt_cloud(
                    segments, src, target_language, prov, remote_model,
                    on_progress=translate_progress,
                    style=translate_style, glossary=glossary,
                )
                translated_text = None
            else:
                translated_text = translate_text_cloud(
                    text, source_language, target_language, prov, remote_model,
                    on_progress=translate_progress, glossary=glossary,
                )
                translated_segments = None
        else:
            # === 本地翻譯 ===
            from app.init.container import get_container
            from app.engine.ai.runtime.llama_server import LlamaServerRuntime
            from app.engine.ai.registry import SLOT_LLM
            from app.utils.translate import translate_srt_local, translate_text_local

            variant = f"{model_size}:{quantization}" if quantization else model_size

            with get_container().model_manager().gpu_session():
                runtime = LlamaServerRuntime(SLOT_LLM)
                translate_progress(0.0, "載入翻譯模型...")

                with runtime.acquire(model_type, variant, lambda p, m: translate_progress(p * 0.05, m)):
                    if is_subtitle:
                        if ext == ".vtt":
                            segments = _parse_vtt(text)
                        else:
                            segments = _parse_srt(text)

                        logger.info(f"Parsed {len(segments)} subtitle segments from {ext} file")
                        src = WHISPER_TO_BCP47.get(source_language, source_language)

                        translate_progress(0.05, "開始翻譯字幕...")
                        translated_segments = translate_srt_local(
                            segments, src, target_language, runtime,
                            on_progress=lambda p, m: translate_progress(0.05 + p * 0.95, m),
                            style=translate_style, glossary=glossary, model_id=model_type,
                        )
                        translated_text = None
                    else:
                        translate_progress(0.05, "開始翻譯...")
                        translated_text = translate_text_local(
                            text, source_language, target_language, runtime,
                            on_progress=lambda p, m: translate_progress(0.05 + p * 0.95, m),
                            glossary=glossary, model_id=model_type,
                        )
                        translated_segments = None

        # === 階段 3: 寫入輸出檔 (95~100%) ===
        progress_callback(0.95, "task.progress.writing_output_file")

        output_file_id = str(uuid4())

        # 決定檔名
        custom_output_filename = params.get("output_filename")
        if custom_output_filename:
            final_filename = custom_output_filename
        else:
            original_stem = Path(file_info.original_filename).stem
            original_ext = Path(file_info.original_filename).suffix or ".txt"
            final_filename = f"{original_stem}_{target_language}{original_ext}"

        # 決定輸出目錄
        custom_output_dir = params.get("output_dir")
        if custom_output_dir:
            output_dir_path = Path(custom_output_dir)
        else:
            output_dir_path = self._file_service.output_dir
        output_dir_path.mkdir(parents=True, exist_ok=True)
        output_path = output_dir_path / final_filename

        # 寫入
        if is_subtitle and translated_segments is not None:
            if ext == ".vtt":
                _write_vtt(translated_segments, output_path)
            else:
                _write_srt(translated_segments, output_path)
        else:
            output_path.write_text(translated_text, encoding="utf-8")

        # 註冊輸出檔案
        output_info = self._file_service.register_output(
            file_id=output_file_id,
            file_path=output_path,
            original_filename=file_info.original_filename,
        )

        progress_callback(1.0, "task.progress.translate_complete")

        if is_subtitle and translated_segments is not None:
            translated_chars = sum(len(s["text"]) for s in translated_segments)
        else:
            translated_chars = len(translated_text)

        return {
            "output_file_id": output_file_id,
            "output_filename": output_info.filename,
            "output_size": output_info.file_size,
            "source_language": source_language,
            "target_language": target_language,
            "source_chars": len(text),
            "translated_chars": translated_chars,
        }
