"""
Subtitle extraction service.
Uses faster-whisper to extract speech from video and generate subtitle files.
"""
import logging
from pathlib import Path
from typing import Any, Callable, Optional
from uuid import uuid4

from app.engine.ffmpeg import FFmpegWrapper
from app.handler.exceptions import FFmpegError
from app.engine.ai.audio.whisper import WhisperWrapper, get_whisper, TranscribeResult
from app.utils.prompts import WHISPER_TO_BCP47
from app.services.files.file_service import FileService
from app.workers.task_manager import TaskManager

logger = logging.getLogger(__name__)

# Task type constant
TASK_TYPE_VIDEO_SUBTITLE_GENERATE = "video.subtitle_generate"


def _format_srt_time(seconds: float) -> str:
    """Format seconds as SRT time format (HH:MM:SS,mmm)."""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds % 1) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def _format_vtt_time(seconds: float) -> str:
    """Format seconds as VTT time format (HH:MM:SS.mmm)."""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds % 1) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}.{millis:03d}"


def _write_srt(result: TranscribeResult, output_path: Path) -> None:
    """Write transcription result in SRT format."""
    with open(output_path, "w", encoding="utf-8") as f:
        for i, seg in enumerate(result.segments, 1):
            f.write(f"{i}\n")
            f.write(f"{_format_srt_time(seg.start)} --> {_format_srt_time(seg.end)}\n")
            f.write(f"{seg.text}\n\n")


def _write_vtt(result: TranscribeResult, output_path: Path) -> None:
    """Write transcription result in VTT format."""
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("WEBVTT\n\n")
        for i, seg in enumerate(result.segments, 1):
            f.write(f"{i}\n")
            f.write(f"{_format_vtt_time(seg.start)} --> {_format_vtt_time(seg.end)}\n")
            f.write(f"{seg.text}\n\n")


class SubtitleService:
    """Subtitle generation from video using FFmpeg audio extraction and Whisper STT."""

    def __init__(self, ffmpeg: FFmpegWrapper, file_service: FileService, task_manager: TaskManager):
        self._ffmpeg = ffmpeg
        self._whisper: WhisperWrapper = get_whisper()
        self._file_service = file_service
        self._task_manager = task_manager

        # Register task handler
        self._task_manager.register_handler(
            TASK_TYPE_VIDEO_SUBTITLE_GENERATE,
            self._handle_task,
        )

        logger.info("SubtitleService initialized")

    def get_model_status(self, model_size: str = "medium") -> dict:
        """Query Whisper model status."""
        return self._whisper.get_model_status(model_size)

    def test_translate(
        self,
        text: str,
        target_language: str = "zh-TW",
        source_language: str = "ja",
        model_size: str = "4b",
        model_family: str = "gemma4",
        thinking: bool = False,
    ) -> dict:
        """
        Test translation (dev use) -- using llama-server messages API.

        Returns:
            dict with keys 'result' and 'prompt'
        """
        from app.utils.inference import get_inference_config, calc_max_tokens, estimate_tokens
        from app.utils.prompts import get_prompt_builder
        from app.engine.ai.runtime.llama_server import LlamaServerRuntime
        from app.engine.ai.registry import SLOT_LLM

        variant = model_size

        config = get_inference_config(model_family, model_size, "translate")
        # Request-level thinking overrides registry default
        use_thinking = thinking or config.get("thinking", False)
        builder = get_prompt_builder("translate", config["prompt_builder"], thinking=use_thinking)
        result = builder(text, source_language, target_language, "text", "colloquial", None)
        input_tokens = estimate_tokens(text)
        max_tokens = calc_max_tokens(config, config["n_ctx"], input_tokens)

        runtime = LlamaServerRuntime(SLOT_LLM)
        with runtime.acquire(model_family, variant):
            if result["mode"] == "chat":
                output = runtime.chat(
                    messages=result["messages"], max_tokens=max_tokens,
                    temperature=config["temperature"],
                    top_k=config.get("top_k", 40), top_p=config.get("top_p", 0.9),
                )
            else:
                output = runtime.complete(
                    prompt=result["prompt"], max_tokens=max_tokens,
                    temperature=config["temperature"],
                    top_k=config.get("top_k", 40), top_p=config.get("top_p", 0.9),
                )

        prompt_info = result.get("messages", [{}])[-1].get("content", "") if result["mode"] == "chat" else result.get("prompt", "")
        return {"result": output, "prompt": prompt_info}

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
        translate_model_family: str = "gemma4",
        translate_quantization: Optional[str] = None,
        # Advanced segmentation parameters
        word_timestamps: bool = False,
        condition_on_previous_text: bool = True,
        min_silence_duration_ms: int = 500,
        vad_threshold: float = 0.5,
        # Translation options
        keep_names: bool = True,
        translate_style: str = "colloquial",
        glossary: Optional[dict[str, str]] = None,
        # Cloud translation
        translate_remote: bool = False,
        translate_provider: Optional[str] = None,
        translate_conn_id: Optional[int] = None,
        translate_remote_model: Optional[str] = None,
    ) -> str:
        """
        Submit a subtitle generation task.

        Args:
            file_id: Input video file ID
            language: Language code (None=auto-detect, "zh"=Chinese, "en"=English...)
            model_size: Model size (tiny, base, small, medium, large-v3)
            output_format: Output format (srt, vtt)
            output_dir: Custom output directory (optional)
            output_filename: Custom output filename (optional)
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
        file_info = self._file_service.get_file(file_id)
        if file_info is None:
            raise ValueError(f"File not found: {file_id}")

        # Build task parameters
        params = {
            "file_id": file_id,
            "language": language,
            "model_size": model_size,
            "output_format": output_format,
            "output_dir": output_dir,
            "output_filename": output_filename,
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
        }

        # Submit task
        task_id = await self._task_manager.submit(TASK_TYPE_VIDEO_SUBTITLE_GENERATE, params)
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
        file_info = self._file_service.get_file(file_id)

        if file_info is None:
            raise ValueError(f"File not found: {file_id}")

        language = params.get("language")  # None = auto detect
        model_size = params.get("model_size", "medium")
        output_format = params.get("output_format", "srt")
        target_language = params.get("target_language")  # None = no translation
        translate_model_size = params.get("translate_model_size", "4b")
        translate_model_family = params.get("translate_model_family", "gemma4")
        translate_quantization = params.get("translate_quantization")

        # Advanced segmentation parameters
        word_timestamps = params.get("word_timestamps", False)
        condition_on_previous_text = params.get("condition_on_previous_text", True)
        min_silence_duration_ms = params.get("min_silence_duration_ms", 500)
        vad_threshold = params.get("vad_threshold", 0.5)

        # Translation options
        keep_names = params.get("keep_names", True)
        translate_style = params.get("translate_style", "colloquial")
        glossary = params.get("glossary")

        has_translation = target_language is not None

        # === Stage 0: Verify video has audio stream ===
        progress_callback(0.0, "task.progress.extracting_audio")

        media_info = self._ffmpeg.get_media_info_sync(file_info.file_path)
        if not media_info.audio_codec:
            raise ValueError("No audio track found in video")

        # === Stage 1: Extract audio (0~10%) ===
        # Create temporary audio path
        temp_audio_path = self._file_service.upload_dir / f"temp_audio_{uuid4().hex[:8]}.wav"

        try:
            self._extract_audio_sync(file_info.file_path, temp_audio_path)
            progress_callback(0.10, "task.progress.audio_extracted")

            # === GPU queue pipeline ===
            # Only one task uses the GPU at a time; models are unloaded after use
            from app.init.container import get_container
            manager = get_container().model_manager()

            with manager.gpu_session():
                # === Stage 2: Speech recognition ===
                # Without translation: 10~90%, with translation: 10~70%
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
                # Whisper is auto-unloaded in transcribe()'s finally block

                # === Forced Alignment (optional) ===
                if params.get("align", False) and result.language:
                    from app.engine.ai.audio.wav2vec2 import get_alignment_engine
                    aligner = get_alignment_engine()
                    if aligner.is_language_supported(result.language):
                        progress_callback(whisper_end - 0.05, "task.progress.aligning")
                        result.segments = aligner.align(
                            audio_path=temp_audio_path,
                            segments=result.segments,
                            language=result.language,
                            on_progress=lambda p, m: progress_callback(whisper_end - 0.05 + p * 0.05, m),
                        )

                # === Stage 3 (optional): Translate subtitles (70~95%) ===
                from app.engine.ai.audio.whisper import TranscribeSegment

                # Save original segments (for bilingual subtitle output when translating)
                original_segments = list(result.segments)

                if has_translation:
                    progress_callback(whisper_end, "task.progress.prepare_translate")

                    seg_dicts = [
                        {"start": s.start, "end": s.end, "text": s.text}
                        for s in result.segments
                    ]

                    def translate_progress(percent: float, msg: str):
                        overall = 0.70 + percent * 0.25
                        progress_callback(overall, msg)

                    src = WHISPER_TO_BCP47.get(result.language, result.language)
                    translate_remote = params.get("translate_remote", False)

                    if translate_remote:
                        # Cloud translation (batch)
                        from app.utils.translate import get_cloud_provider, translate_srt_cloud

                        provider = params.get("translate_provider", "")
                        conn_id = params.get("translate_conn_id")
                        remote_model = params.get("translate_remote_model", "")
                        prov = get_cloud_provider(provider, conn_id, remote_model)

                        translated_all = translate_srt_cloud(
                            seg_dicts, src, target_language, prov, remote_model,
                            on_progress=lambda p, m: translate_progress(0.05 + p * 0.95, m),
                            keep_names=keep_names, style=translate_style, glossary=glossary,
                        )
                        translate_progress(1.0, "task.progress.translate_complete")
                    else:
                        # Local translation
                        from app.engine.ai.runtime.llama_server import LlamaServerRuntime
                        from app.engine.ai.registry import SLOT_LLM
                        from app.utils.translate import translate_srt_local

                        variant = f"{translate_model_size}:{translate_quantization}" if translate_quantization else translate_model_size
                        runtime = LlamaServerRuntime(SLOT_LLM)

                        translate_progress(0.0, "task.progress.load_translate_model")

                        with runtime.acquire(translate_model_family, variant, lambda p, m: translate_progress(p * 0.05, m)):
                            translate_progress(0.05, "task.progress.start_translate")
                            translated_all = translate_srt_local(
                                seg_dicts, src, target_language, runtime,
                                on_progress=lambda p, m: translate_progress(0.05 + p * 0.95, m),
                                keep_names=keep_names, style=translate_style, glossary=glossary,
                                model_family=translate_model_family,
                                model_size=translate_model_size,
                            )

                        translate_progress(1.0, "task.progress.translate_complete")

                    translated = translated_all

                    result.segments = [
                        TranscribeSegment(s["start"], s["end"], s["text"])
                        for s in translated
                    ]

            # === Final stage: Write subtitle file ===
            write_start = 0.95 if has_translation else 0.90
            progress_callback(write_start, "task.progress.generate_file")

            # Determine base filename
            custom_output_filename = params.get("output_filename")
            if custom_output_filename:
                base_name = Path(custom_output_filename).stem
            else:
                base_name = Path(file_info.original_filename).stem

            # Determine output directory (custom dir takes priority over default)
            output_dir = Path(params["output_dir"]) if params.get("output_dir") else self._file_service.output_dir
            output_dir.mkdir(parents=True, exist_ok=True)

            output_files = []

            if has_translation:
                # With translation: output two files
                # 1. Source language subtitles (XXX.<source_lang>.srt)
                source_lang = result.language  # e.g. "ja", "en"
                source_filename = f"{base_name}.{source_lang}.{output_format}"
                source_path = output_dir / source_filename

                # Build source language result (using pre-translation segments)
                from app.engine.ai.audio.whisper import TranscribeResult
                original_result = TranscribeResult(
                    language=result.language,
                    language_probability=result.language_probability,
                    segments=original_segments,  # saved before translation
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

                # 2. Translated subtitles (XXX.<target_lang>.srt)
                target_filename = f"{base_name}.{target_language}.{output_format}"
                target_path = output_dir / target_filename

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

                output_file_id = target_file_id  # primary output is the translated file
                output_filename = target_info.filename
                output_size = target_info.file_size
            else:
                # No translation: output single file (XXX.srt)
                final_filename = f"{base_name}.{output_format}"
                output_path = output_dir / final_filename

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

            progress_callback(1.0, "task.progress.subtitle_complete")

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
            # Clean up temporary audio file
            if temp_audio_path.exists():
                try:
                    temp_audio_path.unlink()
                except OSError:
                    logger.warning(f"Failed to delete temp audio: {temp_audio_path}")

    def _extract_audio_sync(self, input_path: Path, output_path: Path) -> None:
        """
        Extract audio from video as WAV (16kHz, mono) using FFmpeg.

        Optimal input format for faster-whisper: 16kHz mono WAV.
        """
        self._ffmpeg.extract_audio_sync(
            input_path=input_path,
            output_path=output_path,
            audio_format="wav",
            sample_rate=16000,
            channels=1,
        )
