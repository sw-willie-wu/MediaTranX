"""Shared Whisper-based transcribe pipeline.

Pipeline:
  [optional Demucs vocal separation] -> Whisper STT -> [optional wav2vec2 forced alignment]

Callers provide an already-extracted audio file. Video callers extract first via
FFmpegWrapper.extract_audio_sync. Output formatting is in `utils/subtitles.py`.

`model_manager` parameter is optional during the Wave 2→Wave 4 transition: when
None, the pipeline falls back to `get_container().model_manager()`. After Wave 4
§2.1 injects model_manager into the 4 caller services, the fallback can be
dropped and `model_manager` made required.
"""
from __future__ import annotations

import logging
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

logger = logging.getLogger(__name__)


@dataclass
class TranscribeOptions:
    language: Optional[str] = None  # None = auto-detect
    model_size: str = "medium"
    # Whisper advanced
    word_timestamps: bool = False
    condition_on_previous_text: bool = True
    min_silence_duration_ms: int = 200
    vad_threshold: float = 0.3
    # Optional pre: Demucs vocal separation
    separate_vocals: bool = False
    # Optional post: wav2vec2 forced alignment
    align: bool = False


_STAGE_WEIGHTS = {"demucs": 3, "whisper": 5, "align": 1}


def _build_stage_list(options: TranscribeOptions) -> list[str]:
    stages: list[str] = []
    if options.separate_vocals:
        stages.append("demucs")
    stages.append("whisper")
    if options.align:
        stages.append("align")
    return stages


def _make_stage_progress(
    stages: list[str],
    on_progress: Optional[Callable[[float, str], None]],
) -> Callable[[str, float, str], None]:
    """Return a stage_progress(stage, percent, msg) that remaps to overall [0, 1]."""
    if on_progress is None:
        return lambda *a, **kw: None

    total_weight = sum(_STAGE_WEIGHTS[s] for s in stages)

    def _stage(stage: str, percent: float, msg: str) -> None:
        prior = sum(_STAGE_WEIGHTS[s] for s in stages[: stages.index(stage)])
        overall = (prior + _STAGE_WEIGHTS[stage] * percent) / total_weight
        on_progress(overall, msg)

    return _stage


def transcribe_audio_sync(
    audio_path: Path,
    options: TranscribeOptions,
    on_progress: Optional[Callable[[float, str], None]] = None,
    model_manager=None,
    ffmpeg_path: Optional[str] = None,
):
    """[Demucs] -> Whisper -> [align]. Returns faster-whisper TranscribeResult.

    Caller is responsible for: audio extraction from video source (use
    FFmpegWrapper.extract_audio_sync), output file writing, translation,
    and temp file lifecycle of the input audio_path itself. Demucs-separated
    vocals temp file is managed internally.
    """
    # Lazy imports per BACKEND_DEVELOP_SPEC §3.2
    from app.engine.ai.audio.whisper import get_whisper

    if model_manager is None or ffmpeg_path is None:
        from app.init.container import get_container
        container = get_container()
        if model_manager is None:
            model_manager = container.model_manager()
        if ffmpeg_path is None:
            ffmpeg_path = container.ffmpeg().ffmpeg_path

    stages = _build_stage_list(options)
    stage_progress = _make_stage_progress(stages, on_progress)

    temp_vocals: Optional[Path] = None

    try:
        # Stage 1: Demucs vocal separation (optional)
        working_audio = audio_path
        if options.separate_vocals:
            from app.engine.ai.audio.demucs import get_demucs
            import soundfile as sf

            stage_progress("demucs", 0.0, "task.progress.separating_vocals")
            demucs = get_demucs()
            separated, sample_rate = demucs.separate(
                str(audio_path),
                variant="htdemucs_6s",
                stems=["vocals"],
                on_progress=lambda p, m: stage_progress("demucs", p, m),
            )
            vocals = separated.get("vocals")
            if vocals is None:
                raise RuntimeError("Demucs failed to separate vocals")

            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                temp_vocals = Path(tmp.name)
            sf.write(str(temp_vocals), vocals.numpy().T, sample_rate)
            working_audio = temp_vocals
            stage_progress("demucs", 1.0, "task.progress.separation_complete")

        # Stage 2 (Whisper) + Stage 3 (align) share a GPU session
        whisper = get_whisper()
        with model_manager.gpu_session():
            stage_progress("whisper", 0.0, "task.progress.load_whisper")
            result = whisper.transcribe(
                audio_path=working_audio,
                language=options.language,
                model_size=options.model_size,
                on_progress=lambda p, m: stage_progress("whisper", p, m),
                word_timestamps=options.word_timestamps,
                condition_on_previous_text=options.condition_on_previous_text,
                min_silence_duration_ms=options.min_silence_duration_ms,
                vad_threshold=options.vad_threshold,
            )
            stage_progress("whisper", 1.0, "task.progress.recognition_complete")

            if options.align and result.language:
                from app.engine.ai.audio.wav2vec2 import get_alignment_engine

                aligner = get_alignment_engine()
                if aligner.is_language_supported(result.language):
                    stage_progress("align", 0.0, "task.progress.aligning")
                    result.segments = aligner.align(
                        audio_path=working_audio,
                        segments=result.segments,
                        language=result.language,
                        on_progress=lambda p, m: stage_progress("align", p, m),
                        ffmpeg_path=ffmpeg_path,
                    )
                    stage_progress("align", 1.0, "task.progress.align_complete")
                else:
                    logger.info(
                        "Skipping alignment: language %r not supported", result.language
                    )

        return result

    finally:
        if temp_vocals is not None:
            try:
                temp_vocals.unlink(missing_ok=True)
            except OSError as e:
                logger.warning("Failed to clean temp vocals %s: %s", temp_vocals, e)
