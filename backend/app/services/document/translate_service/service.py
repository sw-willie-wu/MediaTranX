"""
Document translation service.
Translates uploaded text files using local LLM.
Supports plain text files and subtitle files (SRT, VTT).
"""
import logging
from pathlib import Path
from typing import Callable, Optional

from app.utils.languages import WHISPER_TO_BCP47
from app.utils.subtitles import (
    Segment,
    format_srt,
    format_vtt,
    parse_srt,
    parse_vtt,
)
from app.utils.bilingual_output import write_bilingual_or_single
from app.adapters.ai.model_manager import ModelManager
from app.services.files.file_service import FileService
from app.services.setup.remote_service import RemoteService
from app.workers.task_manager import TaskManager

logger = logging.getLogger(__name__)

# Task type constant
TASK_TYPE_DOCUMENT_TRANSLATE = "document.translate"

# Subtitle file extensions
SUBTITLE_EXTENSIONS = {".srt", ".vtt", ".lrc", ".ass"}
SUPPORTED_EXTENSIONS = {".txt", ".md", ".log", ".srt", ".vtt", ".lrc", ".ass"}


def _parse_subtitle_file(text: str, ext: str) -> list[dict]:
    """Parse subtitle text to a list of ``{start, end, text}`` dicts.

    The downstream translate helpers (``translate_srt_local`` /
    ``translate_srt_cloud``) consume dict-shaped segments, so we adapt the
    ``Segment`` dataclass from ``app.utils.subtitles`` here.
    """
    segs: list[Segment] = parse_vtt(text) if ext == ".vtt" else parse_srt(text)
    return [{"start": s.start, "end": s.end, "text": s.text} for s in segs]


def _format_subtitle_segments(segments: list[dict], ext: str) -> str:
    """Format translated dict-segments back to SRT/VTT text."""
    seg_list = [Segment(s["start"], s["end"], s["text"]) for s in segments]
    return format_vtt(seg_list) if ext == ".vtt" else format_srt(seg_list)


class TranslateService:
    """Document translation service for text and subtitle files (local and remote)."""

    def __init__(self, file_service: FileService, task_manager: TaskManager,
                 model_manager: ModelManager, chat_service,
                 remote_service: RemoteService):
        self._file_service = file_service
        self._task_manager = task_manager
        self._model_manager = model_manager
        self._chat_service = chat_service
        self._remote_service = remote_service

        # Register task handler
        self._task_manager.register_handler(
            TASK_TYPE_DOCUMENT_TRANSLATE,
            self._handle_task,
            output_policy="history",
        )

        logger.info("TranslateService initialized")

    async def submit_translate(
        self,
        file_id: str,
        source_language: str,
        target_language: str,
        model_size: str = "4b",
        model_family: str = "gemma4",
        quantization: Optional[str] = None,
        translate_style: str = "colloquial",
        glossary: Optional[dict[str, str]] = None,
        remote: bool = False,
        provider: Optional[str] = None,
        conn_id: Optional[int] = None,
        remote_model: Optional[str] = None,
    ) -> str:
        """
        Submit a document translation task.

        Args:
            file_id: Input file ID
            source_language: Source language
            target_language: Target language
            model_size: Model size (4b, 12b, 27b)
            remote: Use cloud provider instead of local LLM
            provider: Cloud provider id (when remote=True)
            conn_id: Cloud connection id (when remote=True)
            remote_model: Cloud model id (when remote=True)

        Returns:
            task_id
        """
        file_info = self._file_service.require_file(file_id)

        params = {
            "file_id": file_id,
            "source_language": source_language,
            "target_language": target_language,
            "model_size": model_size,
            "model_family": model_family,
            "quantization": quantization,
            "translate_style": translate_style,
            "glossary": glossary,
            "remote": remote,
            "provider": provider,
            "conn_id": conn_id,
            "remote_model": remote_model,
        }

        task_id = await self._task_manager.submit(TASK_TYPE_DOCUMENT_TRANSLATE, params)
        logger.info(f"Document translate task submitted: {task_id} for file {file_id}")

        return task_id

    def _handle_task(
        self,
        params: dict,
        progress_callback: Callable[[float, str], None]
    ) -> dict:
        """Handle translation task (runs in executor)."""
        return self._execute(params, progress_callback)

    def _execute(
        self,
        params: dict,
        progress_callback: Callable[[float, str], None]
    ) -> dict:
        """
        Execute document translation.

        Pipeline:
        1. Read file (0~5%)
        2. Translate (5~95%)
        3. Write output file (95~100%)
        """
        file_id = params["file_id"]
        file_info = self._file_service.require_file(file_id)

        source_language = params["source_language"]
        target_language = params["target_language"]
        model_size = params.get("model_size", "4b")
        model_family = params.get("model_family", "gemma4")
        quantization = params.get("quantization")
        translate_style = params.get("translate_style", "colloquial")
        glossary = params.get("glossary")

        # === Stage 1: Read file (0~5%) ===
        progress_callback(0.0, "task.progress.reading_file")

        file_path = Path(file_info.file_path)
        ext = Path(file_info.original_filename).suffix.lower()

        if ext not in SUPPORTED_EXTENSIONS:
            raise ValueError(
                f"Unsupported file format: {ext}. "
                f"Supported: {', '.join(sorted(SUPPORTED_EXTENSIONS))}"
            )

        text = file_path.read_text(encoding="utf-8")
        is_subtitle = ext in SUBTITLE_EXTENSIONS

        progress_callback(0.05, f"task.progress.file_read_complete|{len(text)}")

        # === Stage 2: Translate (5~95%) ===
        def translate_progress(percent: float, msg: str):
            overall = 0.05 + percent * 0.90
            progress_callback(overall, msg)

        is_remote = params.get("remote", False)

        if is_subtitle:
            from app.pipeline.translate import translate_srt_auto

            segments = _parse_subtitle_file(text, ext)
            logger.info(f"Parsed {len(segments)} subtitle segments from {ext} file")
            src = source_language if is_remote else WHISPER_TO_BCP47.get(source_language, source_language)

            if is_remote:
                prov = self._remote_service.get_provider_for_connection(
                    params.get("conn_id"),
                    params.get("provider", ""),
                )
                if prov is None:
                    raise ValueError(f"No available {params.get('provider', '')} connection")
                translated_segments = translate_srt_auto(
                    segments, src, target_language,
                    on_progress=translate_progress,
                    prov=prov,
                    remote_model=params.get("remote_model", ""),
                    style=translate_style,
                    glossary=glossary,
                )
            else:
                # Local SRT translation — no gpu_session wrapper, matching
                # audio/transcribe + video/subtitle pattern (pure-LLM work,
                # chat_service.session's internal acquire is the only
                # serialization needed).
                with self._chat_service.session(
                    model_family=model_family,
                    model_size=model_size,
                    quantization=quantization,
                    on_load_progress=translate_progress,
                    load_band=(0.0, 0.05),
                ) as session:
                    translate_progress(0.05, "task.progress.start_translate")
                    translated_segments = translate_srt_auto(
                        segments, src, target_language,
                        on_progress=lambda p, m: translate_progress(0.05 + p * 0.95, m),
                        session=session,
                        model_family=model_family,
                        model_size=model_size,
                        style=translate_style,
                        glossary=glossary,
                    )
            translated_text = None
        elif is_remote:
            # === Cloud text translation ===
            from .text import translate_text_cloud

            prov = self._remote_service.get_provider_for_connection(
                params.get("conn_id"),
                params.get("provider", ""),
            )
            if prov is None:
                raise ValueError(f"No available {params.get('provider', '')} connection")
            translated_text = translate_text_cloud(
                text, source_language, target_language, prov, params.get("remote_model", ""),
                on_progress=translate_progress, glossary=glossary,
            )
            translated_segments = None
        else:
            # === Local text translation === (pure LLM, no gpu_session wrapper)
            from .text import translate_text_local

            with self._chat_service.session(
                model_family=model_family,
                model_size=model_size,
                quantization=quantization,
                on_load_progress=translate_progress,
                load_band=(0.0, 0.05),
            ) as session:
                translate_progress(0.05, "task.progress.start_translate")
                translated_text = translate_text_local(
                    text, source_language, target_language, session,
                    on_progress=lambda p, m: translate_progress(0.05 + p * 0.95, m),
                    glossary=glossary, model_family=model_family,
                    model_size=model_size,
                )
                translated_segments = None

        # === Stage 3: Write output file (95~100%) ===
        progress_callback(0.95, "task.progress.writing_output_file")

        # Determine filename
        original_stem = Path(file_info.original_filename).stem
        original_ext = Path(file_info.original_filename).suffix or ".txt"
        final_filename = f"{original_stem}_{target_language}{original_ext}"

        # Build output body
        if is_subtitle and translated_segments is not None:
            output_body = _format_subtitle_segments(translated_segments, ext)
            translated_chars = sum(len(s["text"]) for s in translated_segments)
        else:
            output_body = translated_text
            translated_chars = len(translated_text)

        outputs = write_bilingual_or_single(
            source_filename=final_filename,
            source_text=output_body,
            source_lang=target_language,  # doc translate only saves translated output
            target_filename=None,
            target_text=None,
            target_lang=None,
            output_dir=self._file_service.output_dir,
            original_filename=file_info.original_filename,
            file_service=self._file_service,
        )
        out = outputs[0]

        progress_callback(1.0, "task.progress.translate_complete")

        return {
            "output_file_id": out["file_id"],
            "output_filename": out["filename"],
            "output_size": out["size"],
            "source_language": source_language,
            "target_language": target_language,
            "source_chars": len(text),
            "translated_chars": translated_chars,
        }
