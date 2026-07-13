"""
Subtitle extraction service.
Uses faster-whisper to extract speech from video and generate subtitle files.
"""
import logging
from pathlib import Path
from typing import Callable, Optional
from uuid import uuid4

from app.adapters.binary.ffmpeg import FFmpegWrapper
from app.adapters.ai.model_manager import ModelManager
from app.adapters.ai.wrapper.whisper import WhisperWrapper
from app.adapters.ai.wrapper.demucs import DemucsWrapper
from app.adapters.ai.wrapper.wav2vec2 import AlignmentEngine
from app.utils.languages import WHISPER_TO_BCP47
from app.utils.bilingual_output import write_bilingual_or_single
from app.utils.progress_stages import StageProgress
from app.pipeline.transcribe import TranscribeOptions, transcribe_audio_sync
from app.utils.subtitles import Segment, format_srt, format_vtt
from app.services.files.file_service import FileService
from app.services.setup.remote_service import RemoteService
from app.workers.task_manager import TaskManager

logger = logging.getLogger(__name__)

# Task type constant
TASK_TYPE_VIDEO_SUBTITLE = "video.subtitle"


class SubtitleService:
    """Subtitle generation from video using FFmpeg audio extraction and Whisper STT."""

    def __init__(self, ffmpeg: FFmpegWrapper, file_service: FileService, task_manager: TaskManager,
                 model_manager: ModelManager, remote_service: RemoteService,
                 chat_service,
                 whisper: WhisperWrapper,
                 demucs: DemucsWrapper = None,
                 alignment_engine: AlignmentEngine = None):
        self._ffmpeg = ffmpeg
        self._whisper = whisper
        self._demucs = demucs
        self._alignment_engine = alignment_engine
        self._file_service = file_service
        self._task_manager = task_manager
        self._model_manager = model_manager
        self._remote_service = remote_service
        self._chat_service = chat_service

        # Register task handler
        self._task_manager.register_handler(
            TASK_TYPE_VIDEO_SUBTITLE,
            self._handle_task,
            output_policy="results",
        )

        logger.info("SubtitleService initialized")

    def get_model_status(self, model_size: str = "medium") -> dict:
        """Query Whisper model status."""
        return self._whisper.get_model_status(model_size)

    async def submit_subtitle_generate(
        self,
        file_id: str,
        source_language: Optional[str] = None,
        model_size: str = "medium",
        output_format: str = "srt",
        target_language: Optional[str] = None,
        translate_model_size: str = "4b",
        translate_model_family: str = "gemma4",
        translate_quantization: Optional[str] = None,
        # Advanced segmentation parameters
        word_timestamps: bool = False,
        condition_on_previous_text: bool = True,
        min_silence_duration_ms: int = 200,
        vad_threshold: float = 0.3,
        # Translation options
        keep_names: bool = True,
        translate_style: str = "colloquial",
        glossary: Optional[dict[str, str]] = None,
        # Cloud translation
        translate_remote: bool = False,
        translate_provider: Optional[str] = None,
        translate_conn_id: Optional[int] = None,
        translate_remote_model: Optional[str] = None,
        # Preprocessing
        vocal_separation: bool = False,
        # Alignment
        align: bool = False,
        suppress_results: Optional[bool] = None,
    ) -> str:
        """
        Submit a subtitle generation task.

        Args:
            file_id: Input video file ID
            source_language: Language code (None=auto-detect, "zh"=Chinese, "en"=English...)
            model_size: Model size (tiny, base, small, medium, large-v3)
            output_format: Output format (srt, vtt)
            target_language: Translation target language (None=no translation)
            translate_model_size: Translation model size (4b, 12b, 27b)
            word_timestamps: Enable word-level timestamps
            condition_on_previous_text: Whether to condition on previous text for recognition
            min_silence_duration_ms: Minimum silence duration (ms)
            vad_threshold: VAD threshold (0-1)
            keep_names: Preserve proper nouns in original language
            translate_style: Translation style (colloquial/formal/literal)

        Returns:
            task_id: Task ID
        """
        # Validate file exists
        file_info = self._file_service.require_file(file_id)

        # Build task parameters
        params = {
            "file_id": file_id,
            "source_language": source_language,
            "model_size": model_size,
            "output_format": output_format,
            "target_language": target_language,
            "translate_model_size": translate_model_size,
            "translate_model_family": translate_model_family,
            "translate_quantization": translate_quantization,
            "word_timestamps": word_timestamps,
            "condition_on_previous_text": condition_on_previous_text,
            "min_silence_duration_ms": min_silence_duration_ms,
            "vad_threshold": vad_threshold,
            "keep_names": keep_names,
            "translate_style": translate_style,
            "glossary": glossary,
            "translate_remote": translate_remote,
            "translate_provider": translate_provider,
            "translate_conn_id": translate_conn_id,
            "translate_remote_model": translate_remote_model,
            "vocal_separation": vocal_separation,
            "align": align,
        }

        # Submit task
        task_id = await self._task_manager.submit(
            TASK_TYPE_VIDEO_SUBTITLE, params, suppress_results=suppress_results
        )
        logger.info(f"Subtitle generate task submitted: {task_id} for file {file_id}")

        return task_id

    def _handle_task(
        self,
        params: dict,
        progress_callback: Callable[[float, str], None]
    ) -> dict:
        """Handle subtitle generation task (runs in executor)."""
        return self._execute(params, progress_callback)

    def _execute(
        self,
        params: dict,
        progress_callback: Callable[[float, str], None]
    ) -> dict:
        """
        Execute subtitle generation.

        Without translation:
        1. Extract audio from video via FFmpeg (WAV 16kHz mono) -- progress 0~10%
        2. Transcribe audio via faster-whisper -- progress 10~90%
        3. Write segments to SRT/VTT subtitle file -- progress 90~100%

        With translation:
        1. Extract audio from video via FFmpeg -- progress 0~10%
        2. Transcribe audio via faster-whisper -- progress 10~70%
        3. Translate via LLM -- progress 70~95%
        4. Write segments to SRT/VTT subtitle file -- progress 95~100%
        """
        file_id = params["file_id"]
        file_info = self._file_service.require_file(file_id)

        source_language = params.get("source_language")  # None = auto detect
        model_size = params.get("model_size", "medium")
        output_format = params.get("output_format", "srt")
        target_language = params.get("target_language")  # None = no translation
        translate_model_size = params.get("translate_model_size", "4b")
        translate_model_family = params.get("translate_model_family", "gemma4")
        translate_quantization = params.get("translate_quantization")

        # Advanced segmentation parameters
        word_timestamps = params.get("word_timestamps", False)
        condition_on_previous_text = params.get("condition_on_previous_text", True)
        min_silence_duration_ms = params.get("min_silence_duration_ms", 200)
        vad_threshold = params.get("vad_threshold", 0.3)

        # Translation options
        keep_names = params.get("keep_names", True)
        translate_style = params.get("translate_style", "colloquial")
        glossary = params.get("glossary")

        has_translation = target_language is not None

        # === Stage 0: Verify video has audio stream ===
        progress_callback(0.0, "task.progress.extract_audio_starting")

        media_info = self._ffmpeg.get_media_info_sync(file_info.file_path)
        if not media_info.audio_codec:
            raise ValueError("No audio track found in video")

        # === Dynamic progress allocation (via StageProgress) ===
        # With translation: extract=1 / transcribe=6 / translate=2  (~11% / 67% / 22% of pre-final)
        # Without:          extract=1 / transcribe=8                (~11% / 84% of pre-final)
        # Final write stage reserves 5% of overall.
        weights = {"extract": 1, "transcribe": 6 if has_translation else 8}
        if has_translation:
            weights["translate"] = 2
        sp = StageProgress(progress_callback, weights, final_weight=0.05)
        stage_progress = sp.stage

        # === Stage 1: Extract audio ===
        temp_audio_path = self._file_service.upload_dir / f"temp_audio_{uuid4().hex[:8]}.wav"

        try:
            stage_progress("extract", 0.0, "task.progress.extract_audio_starting")
            self._ffmpeg.extract_audio_sync(
                input_path=file_info.file_path,
                output_path=temp_audio_path,
                audio_format="wav",
                sample_rate=16000,
                channels=1,
            )
            stage_progress("extract", 1.0, "task.progress.audio_extracted")

            # === Stage 2: Transcribe ===
            def transcribe_progress(p: float, m: str) -> None:
                stage_progress("transcribe", p, m)

            opts = TranscribeOptions(
                language=source_language,
                model_size=model_size,
                word_timestamps=word_timestamps,
                condition_on_previous_text=condition_on_previous_text,
                min_silence_duration_ms=min_silence_duration_ms,
                vad_threshold=vad_threshold,
                align=params.get("align", False),
                vocal_separation=params.get("vocal_separation", False),
            )
            result = transcribe_audio_sync(
                temp_audio_path, opts,
                self._model_manager,
                self._ffmpeg.ffmpeg_path,
                whisper=self._whisper,
                demucs=self._demucs,
                alignment_engine=self._alignment_engine,
                on_progress=transcribe_progress,
            )

            # Save original segments (for bilingual subtitle output when translating)
            original_segments = list(result.segments)

            # === Stage 3 (optional): Translate subtitles ===
            if has_translation:
                from app.adapters.ai.wrapper.whisper import TranscribeSegment

                stage_progress("translate", 0.0, "task.progress.prepare_translate")

                seg_dicts = [
                    {"start": s.start, "end": s.end, "text": s.text}
                    for s in result.segments
                ]

                def translate_progress(percent: float, msg: str):
                    stage_progress("translate", percent, msg)

                src = WHISPER_TO_BCP47.get(result.language, result.language)
                translate_remote = params.get("translate_remote", False)

                from app.pipeline.translate import translate_srt_auto

                if translate_remote:
                    prov = self._remote_service.get_provider_for_connection(
                        params.get("translate_conn_id"),
                        params.get("translate_provider", ""),
                    )
                    if prov is None:
                        raise ValueError(
                            f"No available {params.get('translate_provider', '')} connection"
                        )
                    translated_all = translate_srt_auto(
                        seg_dicts, src, target_language,
                        on_progress=translate_progress,
                        prov=prov,
                        remote_model=params.get("translate_remote_model", ""),
                        keep_names=keep_names,
                        style=translate_style,
                        glossary=glossary,
                    )
                else:
                    with self._chat_service.session(
                        model_family=translate_model_family,
                        model_size=translate_model_size,
                        quantization=translate_quantization,
                        on_load_progress=lambda p, m: stage_progress("translate", p, m),
                        load_band=(0.0, 0.05),
                    ) as session:
                        translated_all = translate_srt_auto(
                            seg_dicts, src, target_language,
                            on_progress=lambda p, m: stage_progress("translate", 0.05 + p * 0.95, m),
                            session=session,
                            model_family=translate_model_family,
                            model_size=translate_model_size,
                            keep_names=keep_names,
                            style=translate_style,
                            glossary=glossary,
                        )
                translate_progress(1.0, "task.progress.translate_complete")

                translated = translated_all

                result.segments = [
                    TranscribeSegment(s["start"], s["end"], s["text"])
                    for s in translated
                ]

            # === Final stage: Write subtitle file ===
            stage_progress("write", 0.0, "task.progress.generate_file")

            # Convert TranscribeSegments to utils.subtitles Segments for formatting
            source_segments = [Segment(s.start, s.end, s.text) for s in original_segments]
            target_segments = (
                [Segment(s.start, s.end, s.text) for s in result.segments]
                if has_translation
                else None
            )

            # Format per output_format
            if output_format == "srt":
                source_text = format_srt(source_segments)
                target_text = format_srt(target_segments) if target_segments else None
            elif output_format == "vtt":
                source_text = format_vtt(source_segments)
                target_text = format_vtt(target_segments) if target_segments else None
            else:
                raise ValueError(f"Unsupported output format: {output_format}")

            # Determine base filename
            base_name = Path(file_info.original_filename).stem
            output_dir = self._file_service.output_dir

            # Build filenames based on whether translation happened
            if has_translation:
                source_lang = result.language  # e.g. "ja", "en"
                src_filename = f"{base_name}.{source_lang}.{output_format}"
                tgt_filename = f"{base_name}.{target_language}.{output_format}"
            else:
                source_lang = result.language
                src_filename = f"{base_name}.{output_format}"
                tgt_filename = None

            written = write_bilingual_or_single(
                source_filename=src_filename,
                source_text=source_text,
                source_lang=source_lang,
                target_filename=tgt_filename,
                target_text=target_text if has_translation else None,
                target_lang=target_language if has_translation else None,
                output_dir=output_dir,
                original_filename=file_info.original_filename,
                file_service=self._file_service,
            )

            # Annotate with "type" metadata (service-specific, not in helper shape)
            written[0]["type"] = "source"
            if has_translation:
                written[1]["type"] = "translated"

            output_files = written
            # Primary output is the translated file if present, otherwise the source file
            primary = written[1] if has_translation else written[0]
            output_file_id = primary["file_id"]
            output_filename = primary["filename"]
            output_size = primary["size"]

            stage_progress("write", 1.0, "task.progress.subtitle_complete")

            return {
                "output_file_id": output_file_id,
                "output_filename": output_filename,
                "output_size": output_size,
                "output_files": output_files,
                # detected language (frozen output key, distinct from the source_language input param)
                "language": result.language,
                "language_probability": result.language_probability,
                "segment_count": len(result.segments),
                "duration": result.duration,
                "translated": has_translation,
                "target_language": target_language,
            }

        finally:
            # Clean up temporary audio file
            if temp_audio_path.exists():
                try:
                    temp_audio_path.unlink()
                except OSError:
                    logger.warning(f"Failed to delete temp audio: {temp_audio_path}")
