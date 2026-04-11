"""
Audio transcription service.
Uses faster-whisper to convert audio to text.
"""
import logging
import tempfile
from pathlib import Path
from typing import Callable, Optional
from uuid import uuid4

import soundfile as sf

from app.engine.ai.audio.whisper import WhisperWrapper, get_whisper, TranscribeResult
from app.utils.prompts import (
    WHISPER_TO_BCP47,
    parse_srt_response,
    SUMMARIZE_PARAMS,
)
from app.services.files.file_service import FileService
from app.workers.task_manager import TaskManager

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
    """Audio transcription using faster-whisper with optional translation and summarization."""

    def __init__(self, file_service: FileService, task_manager: TaskManager):
        self._whisper: WhisperWrapper = get_whisper()
        self._file_service = file_service
        self._task_manager = task_manager
        self._task_manager.register_handler(TASK_TYPE_AUDIO_TRANSCRIBE, self._handle_task)
        logger.info("AudioTranscribeService initialized")

    def get_model_status(self, model_size: str = "medium") -> dict:
        return self._whisper.get_model_status(model_size)

    async def submit_transcribe(
        self,
        file_id: str,
        language: Optional[str] = None,
        model_size: str = "medium",
        output_format: str = "txt",
        vocal_separation: bool = False,
        align: bool = False,
        translate: bool = False,
        target_lang: Optional[str] = None,
        translate_model_type: str = "translategemma",
        translate_model_size: str = "4b",
        translate_quantization: Optional[str] = None,
        translate_remote: bool = False,
        translate_provider: Optional[str] = None,
        translate_conn_id: Optional[int] = None,
        translate_remote_model: Optional[str] = None,
        summarize: bool = False,
        summarize_model_type: str = "qwen3",
        summarize_model_size: str = "4b",
        summarize_quantization: Optional[str] = None,
        summarize_remote: bool = False,
        summarize_provider: Optional[str] = None,
        summarize_conn_id: Optional[int] = None,
        summarize_remote_model: Optional[str] = None,
        output_dir: Optional[str] = None,
        output_filename: Optional[str] = None,
    ) -> str:
        file_info = self._file_service.get_file(file_id)
        if file_info is None:
            raise ValueError(f"File not found: {file_id}")
        params = {
            "file_id": file_id,
            "language": language,
            "model_size": model_size,
            "output_format": output_format,
            "vocal_separation": vocal_separation,
            "align": align,
            "translate": translate,
            "target_lang": target_lang,
            "translate_model_type": translate_model_type,
            "translate_model_size": translate_model_size,
            "translate_quantization": translate_quantization,
            "translate_remote": translate_remote,
            "translate_provider": translate_provider,
            "translate_conn_id": translate_conn_id,
            "translate_remote_model": translate_remote_model,
            "summarize": summarize,
            "summarize_model_type": summarize_model_type,
            "summarize_model_size": summarize_model_size,
            "summarize_quantization": summarize_quantization,
            "summarize_remote": summarize_remote,
            "summarize_provider": summarize_provider,
            "summarize_conn_id": summarize_conn_id,
            "summarize_remote_model": summarize_remote_model,
            "output_dir": output_dir,
            "output_filename": output_filename,
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
        do_align = params.get("align", False)
        do_translate = params.get("translate", False)
        target_lang = params.get("target_lang")
        do_summarize = params.get("summarize", False)

        original_stem = Path(file_info.original_filename).stem

        # Determine output directory
        output_dir = Path(params["output_dir"]) if params.get("output_dir") else self._file_service.output_dir
        output_dir.mkdir(parents=True, exist_ok=True)

        # Determine base filename
        custom_output_filename = params.get("output_filename")
        if custom_output_filename:
            base_name = Path(custom_output_filename).stem
        else:
            base_name = original_stem

        do_vocal_sep = params.get("vocal_separation", False)
        audio_path = str(file_info.file_path)
        temp_vocals_path = None

        # -- Dynamic progress allocation --
        # Allocate weights based on enabled features; file writing is fixed at 5%
        weights = {"whisper": 5}  # whisper is always required, highest weight
        if do_vocal_sep:  weights["demucs"] = 3
        if do_align:      weights["align"] = 3
        if do_translate:  weights["translate"] = 2
        if do_summarize:  weights["summarize"] = 2
        total_weight = sum(weights.values())

        # Calculate start/end ratio for each stage (last 5% reserved for file writing)
        stages: dict[str, tuple[float, float]] = {}
        cursor = 0.0
        for stage in ["demucs", "whisper", "align", "translate", "summarize"]:
            if stage in weights:
                w = weights[stage] / total_weight * 0.95
                stages[stage] = (cursor, cursor + w)
                cursor += w
        stages["write"] = (0.95, 1.0)

        def stage_progress(stage: str, p: float, msg: str):
            """Report progress within a given stage (p: 0.0~1.0)."""
            s, e = stages.get(stage, (0.0, 1.0))
            progress_callback(s + p * (e - s), msg)

        # === GPU queue pipeline ===
        from app.init.container import get_container
        manager = get_container().model_manager()

        with manager.gpu_session():
            # === Vocal separation ===
            if do_vocal_sep:
                stage_progress("demucs", 0.0, "task.progress.separating_vocals")
                from app.engine.ai.audio.demucs import get_demucs
                demucs = get_demucs()
                separated, sr = demucs.separate(
                    audio_path=audio_path,
                    variant="htdemucs_6s",
                    stems=["vocals"],
                    on_progress=lambda p, m: stage_progress("demucs", p, m),
                )

                vocals = separated.get("vocals")
                if vocals is not None:
                    temp_vocals = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
                    temp_vocals_path = temp_vocals.name
                    temp_vocals.close()
                    sf.write(temp_vocals_path, vocals.T.numpy(), sr)
                    audio_path = temp_vocals_path
                stage_progress("demucs", 1.0, "task.progress.separation_complete")

            try:
                # === Whisper transcription ===
                stage_progress("whisper", 0.0, "task.progress.load_whisper")

                result = self._whisper.transcribe(
                    audio_path=audio_path,
                    language=params.get("language"),
                    model_size=params.get("model_size", "medium"),
                    word_timestamps=do_align,
                    condition_on_previous_text=True,
                    on_progress=lambda p, m: stage_progress("whisper", p, m),
                )

                detected_lang = result.language
                stage_progress("whisper", 1.0, "task.progress.recognition_complete")
            finally:
                if temp_vocals_path:
                    try:
                        Path(temp_vocals_path).unlink(missing_ok=True)
                    except Exception:
                        pass

            # === Wav2Vec2 forced alignment ===
            if do_align and detected_lang:
                from app.engine.ai.audio.wav2vec2 import get_alignment_engine
                aligner = get_alignment_engine()
                if aligner.is_language_supported(detected_lang):
                    stage_progress("align", 0.0, "task.progress.aligning")
                    result.segments = aligner.align(
                        audio_path=str(file_info.file_path),
                        segments=result.segments,
                        language=detected_lang,
                        on_progress=lambda p, m: stage_progress("align", p, m),
                    )
                    stage_progress("align", 1.0, "task.progress.align_complete")

        # === Translation ===
        from app.engine.ai.audio.whisper import TranscribeSegment

        original_segments = list(result.segments)

        if do_translate and target_lang:
            stage_progress("translate", 0.0, "task.progress.prepare_translate_audio")

            translate_remote = params.get("translate_remote", False)

            if translate_remote:
                # Cloud translation (batch)
                from app.utils.translate import get_cloud_provider, translate_srt_cloud

                provider = params.get("translate_provider", "")
                conn_id = params.get("translate_conn_id")
                remote_model = params.get("translate_remote_model", "")
                prov = get_cloud_provider(provider, conn_id, remote_model)

                seg_dicts = [{"start": s.start, "end": s.end, "text": s.text} for s in result.segments]
                translated_all = translate_srt_cloud(
                    seg_dicts, detected_lang, target_lang, prov, remote_model,
                    on_progress=lambda p, m: stage_progress("translate", p, m),
                )

                result.segments = [
                    TranscribeSegment(s["start"], s["end"], s["text"])
                    for s in translated_all
                ]
            else:
                # Local translation
                from app.engine.ai.runtime.llama_server import LlamaServerRuntime
                from app.engine.ai.registry import SLOT_LLM
                from app.utils.translate import translate_srt_local

                translate_model_type = params.get("translate_model_type", "translategemma")
                translate_model_size = params.get("translate_model_size", "4b")
                translate_quantization = params.get("translate_quantization")

                seg_dicts = [
                    {"start": s.start, "end": s.end, "text": s.text}
                    for s in result.segments
                ]

                variant = f"{translate_model_size}:{translate_quantization}" if translate_quantization else translate_model_size
                src = WHISPER_TO_BCP47.get(detected_lang, detected_lang)
                runtime = LlamaServerRuntime(SLOT_LLM)

                stage_progress("translate", 0.0, "task.progress.load_translate_model")

                with runtime.acquire(translate_model_type, variant, lambda p, m: stage_progress("translate", p * 0.05, m)):
                    stage_progress("translate", 0.05, "task.progress.start_translate")
                    translated_all = translate_srt_local(
                        seg_dicts, src, target_lang, runtime,
                        on_progress=lambda p, m: stage_progress("translate", 0.05 + p * 0.95, m),
                        model_id=translate_model_type,
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
                from app.utils.translate import get_cloud_provider
                provider = params.get("summarize_provider", "")
                conn_id = params.get("summarize_conn_id")
                remote_model = params.get("summarize_remote_model", "")
                prov = get_cloud_provider(provider, conn_id, remote_model)

                def _cloud_chat(prompt: str, max_tokens: int = 2048) -> str:
                    return prov.chat(
                        model=remote_model,
                        messages=[{"role": "user", "content": prompt}],
                        max_tokens=max_tokens, temperature=0.3,
                    )

                from app.utils.summarize import map_reduce_summarize
                summary_text = map_reduce_summarize(
                    full_text, _cloud_chat,
                    on_progress=lambda p, m: stage_progress("summarize", p, m),
                )
            else:
                # Local map-reduce
                from app.engine.ai.runtime.llama_server import LlamaServerRuntime
                from app.engine.ai.registry import SLOT_LLM
                summary_model_id = params.get("summarize_model_type", "qwen3")
                summary_model_size = params.get("summarize_model_size", "4b")
                summary_quantization = params.get("summarize_quantization")
                summary_variant = f"{summary_model_size}:{summary_quantization}" if summary_quantization else summary_model_size
                runtime = LlamaServerRuntime(SLOT_LLM)

                with runtime.acquire(summary_model_id, summary_variant):
                    def _local_chat(prompt: str, max_tokens: int = 2048) -> str:
                        return runtime.chat(
                            messages=[{"role": "user", "content": prompt}],
                            max_tokens=max_tokens, temperature=0.3,
                        )

                    from app.utils.summarize import map_reduce_summarize
                    summary_text = map_reduce_summarize(
                        full_text, _local_chat,
                        on_progress=lambda p, m: stage_progress("summarize", p, m),
                    )

            stage_progress("summarize", 1.0, "task.progress.summary_complete")

        # === Write output files ===
        stage_progress("write", 0.0, "task.progress.writing_file")

        output_files = []

        if do_translate and target_lang:
            # With translation: output two files
            # 1. Source language transcript
            source_filename = f"{base_name}.{detected_lang}.{output_format}"
            source_path = output_dir / source_filename
            source_result = TranscribeResult(
                segments=original_segments, language=detected_lang,
                language_probability=result.language_probability, duration=result.duration,
            )
            if output_format == "srt":
                _write_srt(source_result, source_path)
            else:
                _write_txt(source_result, source_path)

            source_file_id = str(uuid4())
            source_info = self._file_service.register_output(
                file_id=source_file_id,
                file_path=source_path,
                original_filename=file_info.original_filename,
            )
            output_files.append({
                "file_id": source_file_id,
                "filename": source_info.filename,
                "language": detected_lang,
                "type": "source",
            })

            # 2. Translated transcript
            target_filename = f"{base_name}.{target_lang}.{output_format}"
            target_path = output_dir / target_filename
            target_result = TranscribeResult(
                segments=result.segments, language=target_lang,
                language_probability=result.language_probability, duration=result.duration,
            )
            if output_format == "srt":
                _write_srt(target_result, target_path)
            else:
                _write_txt(target_result, target_path)

            target_file_id = str(uuid4())
            target_info = self._file_service.register_output(
                file_id=target_file_id,
                file_path=target_path,
                original_filename=file_info.original_filename,
            )
            output_files.append({
                "file_id": target_file_id,
                "filename": target_info.filename,
                "language": target_lang,
                "type": "translated",
            })

            output_file_id = target_file_id
            output_filename_result = target_info.filename
        else:
            # No translation: output single file
            final_filename = f"{base_name}.{output_format}"
            output_path = output_dir / final_filename
            if output_format == "srt":
                _write_srt(result, output_path)
            else:
                _write_txt(result, output_path)

            output_file_id = str(uuid4())
            output_info = self._file_service.register_output(
                file_id=output_file_id,
                file_path=output_path,
                original_filename=file_info.original_filename,
            )
            output_files.append({
                "file_id": output_file_id,
                "filename": output_info.filename,
                "language": detected_lang,
                "type": "source",
            })
            output_filename_result = output_info.filename

        # Write summary file
        if summary_text:
            summary_filename = f"{base_name}.draft.txt"
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
        text_content = None
        if output_files:
            try:
                fid = output_files[0]["file_id"]
                info = self._file_service.get_file(fid)
                if info and info.file_path:
                    with open(info.file_path, "r", encoding="utf-8") as f:
                        text_content = f.read()
            except Exception:
                pass

        return {
            "output_file_id": output_file_id,
            "output_filename": output_filename_result,
            "output_dir": str(output_dir),
            "output_files": output_files,
            "text_file_id": output_file_id,
            "text_content": text_content,
            "detected_language": detected_lang,
            "segment_count": len(result.segments),
            "translated": do_translate and target_lang is not None,
            "target_language": target_lang,
            "summarized": do_summarize,
        }
