"""
Lyrics extraction service.
Uses Demucs vocal separation + Whisper speech recognition to extract lyrics from music.
"""
import logging
from pathlib import Path
from typing import Callable, Optional

from app.adapters.ai.model_manager import ModelManager
from app.adapters.binary.ffmpeg import FFmpegWrapper
from app.utils.languages import WHISPER_TO_BCP47
from app.utils.bilingual_output import write_bilingual_or_single
from app.utils.progress_stages import StageProgress
from app.pipeline.transcribe import TranscribeOptions, transcribe_audio_sync
from app.services.files.file_service import FileService
from app.services.setup.remote_service import RemoteService
from app.workers.task_manager import TaskManager

logger = logging.getLogger(__name__)

TASK_TYPE_AUDIO_LYRICS = "audio.lyrics"


class AudioLyricsService:
    """Lyrics extraction using Demucs vocal separation and Whisper transcription."""

    def __init__(self, file_service: FileService, task_manager: TaskManager,
                 ffmpeg: FFmpegWrapper, model_manager: ModelManager,
                 llama_runtime, remote_service: RemoteService):
        self._file_service = file_service
        self._task_manager = task_manager
        self._ffmpeg = ffmpeg
        self._model_manager = model_manager
        self._llama_runtime = llama_runtime
        self._remote_service = remote_service
        self._task_manager.register_handler(
            TASK_TYPE_AUDIO_LYRICS, self._handle_task,
            output_policy="results",
        )
        logger.info("AudioLyricsService initialized")

    async def submit_lyrics(
        self,
        file_id: str,
        whisper_model: str = "faster-whisper",
        whisper_size: str = "medium",
        align: bool = False,
        translate: bool = False,
        target_lang: Optional[str] = None,
        translate_model_family: str = "gemma4",
        translate_model_size: str = "4b",
        translate_quantization: Optional[str] = None,
        translate_remote: bool = False,
        translate_provider: Optional[str] = None,
        translate_conn_id: Optional[int] = None,
        translate_remote_model: Optional[str] = None,
        output_format: str = "lrc",
    ) -> str:
        file_info = self._file_service.require_file(file_id)
        params = {
            "file_id": file_id,
            "whisper_model": whisper_model,
            "whisper_size": whisper_size,
            "align": align,
            "translate": translate,
            "target_lang": target_lang,
            "translate_model_family": translate_model_family,
            "translate_model_size": translate_model_size,
            "translate_quantization": translate_quantization,
            "translate_remote": translate_remote,
            "translate_provider": translate_provider,
            "translate_conn_id": translate_conn_id,
            "translate_remote_model": translate_remote_model,
            "output_format": output_format,
        }
        task_id = await self._task_manager.submit(TASK_TYPE_AUDIO_LYRICS, params)
        logger.info(f"Audio lyrics task submitted: {task_id}")
        return task_id

    def _handle_task(self, params: dict, progress_callback: Callable[[float, str], None]) -> dict:
        return self._execute(params, progress_callback)

    def _execute(self, params: dict, progress_callback: Callable[[float, str], None]) -> dict:
        file_id = params["file_id"]
        file_info = self._file_service.require_file(file_id)

        whisper_size = params.get("whisper_size", "medium")
        do_translate = params.get("translate", False)
        target_lang = params.get("target_lang")
        output_format = params.get("output_format", "lrc")

        original_stem = Path(file_info.original_filename).stem

        output_dir = self._file_service.output_dir
        base_name = original_stem

        # -- Dynamic progress allocation --
        # Lyrics ALWAYS run demucs + whisper + align; translation is optional.
        weights = {"demucs": 3, "whisper": 5, "align": 3}
        if do_translate:  weights["translate"] = 2

        sp = StageProgress(progress_callback, weights)
        stage_progress = sp.stage

        # === Transcribe (Demucs + Whisper + align) via shared primitive ===
        opts = TranscribeOptions(
            language=params.get("language"),
            model_size=whisper_size,
            word_timestamps=True,  # lyrics need word-level timing for alignment
            condition_on_previous_text=params.get("condition_on_previous_text", True),
            min_silence_duration_ms=params.get("min_silence_duration_ms", 200),
            vad_threshold=params.get("vad_threshold", 0.3),
            separate_vocals=True,  # lyrics ALWAYS use demucs
            align=True,            # lyrics ALWAYS align
        )

        # The primitive's 0..1 progress spans demucs -> whisper -> align.
        transcribe_start = sp.range("demucs")[0]
        transcribe_end = sp.range("align")[1]

        def transcribe_progress(p: float, m: str) -> None:
            progress_callback(
                transcribe_start + p * (transcribe_end - transcribe_start), m
            )

        result = transcribe_audio_sync(
            file_info.file_path,
            opts,
            self._model_manager,
            self._ffmpeg.ffmpeg_path,
            on_progress=transcribe_progress,
        )
        detected_lang = result.language

        # === Translation ===
        from app.adapters.ai.wrapper.whisper import TranscribeSegment

        original_segments = list(result.segments)

        if do_translate and target_lang:
            stage_progress("translate", 0.0, "task.progress.lyrics_prepare_translate")

            translate_remote = params.get("translate_remote", False)

            from app.pipeline.translate import translate_srt_auto

            seg_dicts = [{"start": s.start, "end": s.end, "text": s.text} for s in result.segments]
            src = detected_lang if translate_remote else WHISPER_TO_BCP47.get(detected_lang, detected_lang)

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
                    seg_dicts, src, target_lang,
                    on_progress=lambda p, m: stage_progress("translate", p, m),
                    prov=prov,
                    remote_model=params.get("translate_remote_model", ""),
                )
            else:
                translated_all = translate_srt_auto(
                    seg_dicts, src, target_lang,
                    on_progress=lambda p, m: stage_progress("translate", p, m),
                    llama_runtime=self._llama_runtime,
                    model_family=params.get("translate_model_family", "gemma4"),
                    model_size=params.get("translate_model_size", "4b"),
                    quantization=params.get("translate_quantization"),
                    load_msg="task.progress.lyrics_load_translate",
                    start_msg="task.progress.lyrics_translating",
                )

            if not translate_remote:
                stage_progress("translate", 1.0, "task.progress.lyrics_translate_complete")

            result.segments = [
                TranscribeSegment(s["start"], s["end"], s["text"])
                for s in translated_all
            ]

        # === Write output files ===
        stage_progress("write", 0.0, "task.progress.lyrics_writing")

        if do_translate and target_lang:
            src_filename = f"{base_name}.{detected_lang}.{output_format}"
            tgt_filename = f"{base_name}.{target_lang}.{output_format}"
            source_text = self._format_output(original_segments, output_format)
            target_text = self._format_output(result.segments, output_format)
        else:
            src_filename = f"{base_name}.{output_format}"
            tgt_filename = None
            source_text = self._format_output(result.segments, output_format)
            target_text = None

        written = write_bilingual_or_single(
            source_filename=src_filename,
            source_text=source_text,
            source_lang=detected_lang,
            target_filename=tgt_filename,
            target_text=target_text,
            target_lang=target_lang if (do_translate and target_lang) else None,
            output_dir=output_dir,
            original_filename=file_info.original_filename,
            file_service=self._file_service,
        )

        # Annotate "type" (service-specific metadata, not in helper shape)
        written[0]["type"] = "source"
        if do_translate and target_lang:
            written[1]["type"] = "translated"

        output_files = written
        primary = written[1] if (do_translate and target_lang) else written[0]
        output_file_id = primary["file_id"]
        output_filename_result = primary["filename"]

        progress_callback(1.0, "task.progress.lyrics_complete")

        # Read lyrics content for preview
        text_content = self._file_service.read_text(output_files[0]["file_id"]) if output_files else None

        return {
            "output_file_id": output_file_id,
            "output_filename": output_filename_result,
            "output_files": output_files,
            "text_file_id": output_file_id,
            "text_content": text_content,
            "detected_language": detected_lang,
            "segment_count": len(result.segments),
            "translated": do_translate and target_lang is not None,
            "target_language": target_lang,
        }

    @staticmethod
    def _format_output(segments, output_format: str) -> str:
        """Format lyrics segments to text in the specified format."""
        from app.utils.subtitles import Segment, format_lrc, format_txt

        seg_list = [Segment(s.start, s.end, s.text) for s in segments]
        if output_format == "lrc":
            return format_lrc(seg_list)
        # txt: plain text, one line per segment
        return format_txt(seg_list)
