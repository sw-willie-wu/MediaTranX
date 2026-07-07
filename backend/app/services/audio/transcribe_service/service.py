"""
Audio transcription service.
Uses faster-whisper to convert audio to text.
"""
import logging
from pathlib import Path
from typing import Callable, Optional
from uuid import uuid4

from app.adapters.ai.wrapper.whisper import WhisperWrapper
from app.adapters.ai.wrapper.demucs import DemucsWrapper
from app.adapters.ai.wrapper.wav2vec2 import AlignmentEngine
from app.adapters.binary.ffmpeg import FFmpegWrapper
from app.adapters.ai.model_manager import ModelManager
from app.utils.languages import WHISPER_TO_BCP47
from app.utils.bilingual_output import write_bilingual_or_single
from app.utils.progress_stages import StageProgress
from app.pipeline.transcribe import TranscribeOptions, transcribe_audio_sync
from app.services.files.file_service import FileService
from app.services.setup.remote_service import RemoteService
from app.workers.task_manager import TaskManager

logger = logging.getLogger(__name__)

TASK_TYPE_AUDIO_TRANSCRIBE = "audio.transcribe"


class AudioTranscribeService:
    """Audio transcription using faster-whisper with optional translation and summarization."""

    def __init__(self, file_service: FileService, task_manager: TaskManager,
                 ffmpeg: FFmpegWrapper, model_manager: ModelManager,
                 remote_service: RemoteService,
                 chat_service,
                 whisper: WhisperWrapper,
                 demucs: DemucsWrapper = None,
                 alignment_engine: AlignmentEngine = None):
        self._whisper = whisper
        self._demucs = demucs
        self._alignment_engine = alignment_engine
        self._file_service = file_service
        self._task_manager = task_manager
        self._ffmpeg = ffmpeg
        self._model_manager = model_manager
        self._remote_service = remote_service
        self._chat_service = chat_service
        self._task_manager.register_handler(
            TASK_TYPE_AUDIO_TRANSCRIBE, self._handle_task,
            output_policy="results",
        )
        logger.info("AudioTranscribeService initialized")

    def get_model_status(self, model_size: str = "medium") -> dict:
        return self._whisper.get_model_status(model_size)

    async def submit_transcribe(
        self,
        file_id: str,
        source_language: Optional[str] = None,
        model_size: str = "medium",
        output_format: str = "txt",
        vocal_separation: bool = False,
        align: bool = False,
        translate: bool = False,
        target_language: Optional[str] = None,
        translate_model_family: str = "gemma4",
        translate_model_size: str = "4b",
        translate_quantization: Optional[str] = None,
        translate_remote: bool = False,
        translate_provider: Optional[str] = None,
        translate_conn_id: Optional[int] = None,
        translate_remote_model: Optional[str] = None,
        summarize: bool = False,
        summarize_model_family: str = "gemma4",
        summarize_model_size: str = "4b",
        summarize_quantization: Optional[str] = None,
        summarize_remote: bool = False,
        summarize_provider: Optional[str] = None,
        summarize_conn_id: Optional[int] = None,
        summarize_remote_model: Optional[str] = None,
        word_timestamps: bool = False,
        condition_on_previous_text: bool = True,
        min_silence_duration_ms: int = 200,
        vad_threshold: float = 0.3,
        keep_names: bool = True,
        translate_style: str = "colloquial",
        glossary: Optional[dict] = None,
        suppress_results: bool = False,
    ) -> str:
        file_info = self._file_service.require_file(file_id)
        params = {
            "file_id": file_id,
            "source_language": source_language,
            "model_size": model_size,
            "output_format": output_format,
            "vocal_separation": vocal_separation,
            "align": align,
            "translate": translate,
            "target_language": target_language,
            "translate_model_family": translate_model_family,
            "translate_model_size": translate_model_size,
            "translate_quantization": translate_quantization,
            "translate_remote": translate_remote,
            "translate_provider": translate_provider,
            "translate_conn_id": translate_conn_id,
            "translate_remote_model": translate_remote_model,
            "summarize": summarize,
            "summarize_model_family": summarize_model_family,
            "summarize_model_size": summarize_model_size,
            "summarize_quantization": summarize_quantization,
            "summarize_remote": summarize_remote,
            "summarize_provider": summarize_provider,
            "summarize_conn_id": summarize_conn_id,
            "summarize_remote_model": summarize_remote_model,
            "word_timestamps": word_timestamps,
            "condition_on_previous_text": condition_on_previous_text,
            "min_silence_duration_ms": min_silence_duration_ms,
            "vad_threshold": vad_threshold,
            "keep_names": keep_names,
            "translate_style": translate_style,
            "glossary": glossary,
        }
        task_id = await self._task_manager.submit(
            TASK_TYPE_AUDIO_TRANSCRIBE, params, suppress_results=suppress_results
        )
        logger.info(f"Audio transcribe task submitted: {task_id}")
        return task_id

    def _handle_task(self, params: dict, progress_callback: Callable[[float, str], None]) -> dict:
        return self._execute(params, progress_callback)

    def _execute(self, params: dict, progress_callback: Callable[[float, str], None]) -> dict:
        file_id = params["file_id"]
        file_info = self._file_service.require_file(file_id)

        output_format = params.get("output_format", "txt")
        do_align = params.get("align", False)
        do_translate = params.get("translate", False)
        target_language = params.get("target_language")
        do_summarize = params.get("summarize", False)

        original_stem = Path(file_info.original_filename).stem

        output_dir = self._file_service.output_dir
        base_name = original_stem

        do_vocal_sep = params.get("vocal_separation", False)

        # -- Dynamic progress allocation --
        # Allocate weights based on enabled features; file writing is fixed at 5%.
        # The shared transcribe primitive covers demucs+whisper+align as one span;
        # we still keep their individual weights here for overall progress remap.
        # Build dict in canonical order for stable cursor advancement.
        weights = {}
        if do_vocal_sep:  weights["demucs"] = 3
        weights["whisper"] = 5  # whisper is always required, highest weight
        if do_align:      weights["align"] = 3
        if do_translate:  weights["translate"] = 2
        if do_summarize:  weights["summarize"] = 2

        sp = StageProgress(progress_callback, weights)
        stage_progress = sp.stage

        # === Transcribe (Demucs + Whisper + align) via shared primitive ===
        # Wave 2: word_timestamps is UI/request-controlled and decoupled from align.
        # Enabling align no longer implies word_timestamps (conscious decision); users
        # who want word-level segmentation (_split_by_words) enable word_timestamps explicitly.
        opts = TranscribeOptions(
            language=params.get("source_language"),
            model_size=params.get("model_size", "medium"),
            word_timestamps=params.get("word_timestamps", False),
            condition_on_previous_text=params.get("condition_on_previous_text", True),
            min_silence_duration_ms=params.get("min_silence_duration_ms", 200),
            vad_threshold=params.get("vad_threshold", 0.3),
            vocal_separation=do_vocal_sep,
            align=do_align,
        )

        # Compute the transcribe primitive's overall span in this service's
        # progress timeline: it covers whichever of demucs/whisper/align are active.
        first_stage = "demucs" if do_vocal_sep else "whisper"
        last_stage = "align" if do_align else "whisper"
        transcribe_start = sp.range(first_stage)[0]
        transcribe_end = sp.range(last_stage)[1]

        def transcribe_progress(p: float, m: str) -> None:
            progress_callback(
                transcribe_start + p * (transcribe_end - transcribe_start), m
            )

        # Source is already audio — no FFmpeg extract step needed.
        result = transcribe_audio_sync(
            file_info.file_path,
            opts,
            self._model_manager,
            self._ffmpeg.ffmpeg_path,
            whisper=self._whisper,
            demucs=self._demucs,
            alignment_engine=self._alignment_engine,
            on_progress=transcribe_progress,
        )
        detected_lang = result.language

        # === Translation ===
        from app.adapters.ai.wrapper.whisper import TranscribeSegment

        original_segments = list(result.segments)

        if do_translate and target_language:
            stage_progress("translate", 0.0, "task.progress.prepare_translate_audio")

            translate_remote = params.get("translate_remote", False)

            from app.pipeline.translate import translate_srt_auto

            seg_dicts = [{"start": s.start, "end": s.end, "text": s.text} for s in result.segments]
            src = detected_lang if translate_remote else WHISPER_TO_BCP47.get(detected_lang, detected_lang)

            translate_remote_model = params.get("translate_remote_model", "")
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
                    on_progress=lambda p, m: stage_progress("translate", p, m),
                    prov=prov,
                    remote_model=translate_remote_model,
                    keep_names=params.get("keep_names", True),
                    style=params.get("translate_style", "colloquial"),
                    glossary=params.get("glossary"),
                )
            else:
                translate_model_family = params.get("translate_model_family", "gemma4")
                translate_model_size = params.get("translate_model_size", "4b")
                translate_quantization = params.get("translate_quantization")
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
                        keep_names=params.get("keep_names", True),
                        style=params.get("translate_style", "colloquial"),
                        glossary=params.get("glossary"),
                    )

            result.segments = [
                TranscribeSegment(s["start"], s["end"], s["text"])
                for s in translated_all
            ]

        # === Summarization ===
        summary_text = None
        if do_summarize:
            stage_progress("summarize", 0.0, "task.progress.generating_summary")

            # Text for summarization: use translated text if available, otherwise original
            if do_translate:
                full_text = "\n".join(s.text.strip() for s in result.segments)
            else:
                full_text = "\n".join(s.text.strip() for s in original_segments)

            summarize_remote = params.get("summarize_remote", False)

            if summarize_remote:
                # Cloud map-reduce
                from app.adapters.ai.inference_config import get_remote_inference_config

                provider = params.get("summarize_provider", "")
                conn_id = params.get("summarize_conn_id")
                remote_model = params.get("summarize_remote_model", "")
                prov = self._remote_service.get_provider_for_connection(conn_id, provider)
                if prov is None:
                    raise ValueError(f"No available {provider} connection")
                remote_config = get_remote_inference_config("summarize")

                from app.services.llm.remote_chat import RemoteChatSession
                summary_session = RemoteChatSession(
                    prov, remote_model,
                    on_progress=lambda p, m: stage_progress("summarize", p, m),
                )

                def _cloud_chat(prompt: str, max_tokens: int = 2048) -> str:
                    return summary_session.chat(
                        messages=[{"role": "user", "content": prompt}],
                        max_tokens=max_tokens,
                        temperature=remote_config["temperature"],
                    )

                from .summarize import map_reduce_summarize, calc_chunk_budget
                from app.pipeline.translate import get_cloud_ctx
                source_language = WHISPER_TO_BCP47.get(detected_lang, detected_lang)
                cloud_ctx = get_cloud_ctx(prov, remote_model)
                chunk_tokens = calc_chunk_budget(cloud_ctx)
                summary_text = map_reduce_summarize(
                    full_text, _cloud_chat,
                    source_lang=source_language,
                    on_progress=lambda p, m: stage_progress("summarize", p, m),
                    max_tokens_per_chunk=chunk_tokens,
                )
            else:
                # Local map-reduce
                from app.adapters.ai.inference_config import get_inference_config

                summary_model_family = params.get("summarize_model_family", "gemma4")
                summary_model_size = params.get("summarize_model_size", "4b")
                summary_quantization = params.get("summarize_quantization")

                config = get_inference_config(summary_model_family, summary_model_size, "summarize")

                with self._chat_service.session(
                    model_family=summary_model_family,
                    model_size=summary_model_size,
                    quantization=summary_quantization,
                ) as session:
                    def _local_chat(prompt: str, max_tokens: int = 2048) -> str:
                        return session.chat(
                            messages=[{"role": "user", "content": prompt}],
                            max_tokens=max_tokens,
                            temperature=config["temperature"],
                            top_k=config.get("top_k", 40),
                            top_p=config.get("top_p", 0.9),
                        )

                    from .summarize import map_reduce_summarize, calc_chunk_budget
                    source_language = WHISPER_TO_BCP47.get(detected_lang, detected_lang)
                    chunk_tokens = calc_chunk_budget(config["n_ctx"])
                    summary_text = map_reduce_summarize(
                        full_text, _local_chat,
                        source_lang=source_language,
                        on_progress=lambda p, m: stage_progress("summarize", p, m),
                        max_tokens_per_chunk=chunk_tokens,
                        cancellable=session,
                    )

            stage_progress("summarize", 1.0, "task.progress.summary_complete")

        # === Write output files ===
        from app.utils.subtitles import (
            Segment,
            format_srt,
            format_txt,
            format_vtt,
        )

        stage_progress("write", 0.0, "task.progress.writing_file")

        def _format_segments(segs) -> str:
            seg_list = [Segment(s.start, s.end, s.text) for s in segs]
            if output_format == "srt":
                return format_srt(seg_list)
            if output_format == "vtt":
                return format_vtt(seg_list)
            return format_txt(seg_list)

        if do_translate and target_language:
            src_filename = f"{base_name}.{detected_lang}.{output_format}"
            tgt_filename = f"{base_name}.{target_language}.{output_format}"
            source_text = _format_segments(original_segments)
            target_text = _format_segments(result.segments)
        else:
            src_filename = f"{base_name}.{output_format}"
            tgt_filename = None
            source_text = _format_segments(result.segments)
            target_text = None

        written = write_bilingual_or_single(
            source_filename=src_filename,
            source_text=source_text,
            source_lang=detected_lang,
            target_filename=tgt_filename,
            target_text=target_text,
            target_lang=target_language if (do_translate and target_language) else None,
            output_dir=output_dir,
            original_filename=file_info.original_filename,
            file_service=self._file_service,
        )

        # Annotate "type" (service-specific metadata not in helper shape)
        written[0]["type"] = "source"
        if do_translate and target_language:
            written[1]["type"] = "translated"

        output_files = written
        primary = written[1] if (do_translate and target_language) else written[0]
        output_file_id = primary["file_id"]
        output_filename_result = primary["filename"]

        # Write summary file
        if summary_text:
            summary_filename = f"{base_name}.draft.md"
            summary_path = output_dir / summary_filename
            with open(summary_path, "w", encoding="utf-8") as f:
                f.write(summary_text)

            summary_file_id = str(uuid4())
            summary_info = self._file_service.register_output(
                file_id=summary_file_id,
                file_path=summary_path,
                original_filename=file_info.original_filename,
            )
            output_files.append({
                "file_id": summary_file_id,
                "filename": summary_info.filename,
                "language": detected_lang,
                "type": "summary",
            })

        progress_callback(1.0, "task.progress.transcribe_complete")

        # Read transcript content for preview
        text_content = self._file_service.read_text(output_files[0]["file_id"]) if output_files else None

        return {
            "output_file_id": output_file_id,
            "output_filename": output_filename_result,
            "output_dir": str(output_dir),
            "output_files": output_files,
            "text_file_id": output_file_id,
            "text_content": text_content,
            "detected_language": detected_lang,
            "segment_count": len(result.segments),
            "translated": do_translate and target_language is not None,
            "target_language": target_language,
            "summarized": do_summarize,
        }
