"""Shared Whisper-based transcribe pipeline.

Pipeline:
  [optional Demucs vocal separation] -> Whisper STT -> [optional wav2vec2 forced alignment]

Callers provide an already-extracted audio file + the AI resources the pipeline
needs (`model_manager`, `ffmpeg_path`). Video callers extract first via
FFmpegWrapper.extract_audio_sync. Output formatting is in `utils/subtitles.py`.

Per spec §1.4, pipeline/ cannot import init/ — callers must inject the required
resources explicitly.
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
    # None = auto-detect. Field name mirrors Whisper's own `language` arg (kept
    # despite the payload contract key being `source_language` — see naming §1.3.6).
    language: Optional[str] = None
    model_size: str = "medium"
    # Whisper advanced
    word_timestamps: bool = False
    condition_on_previous_text: bool = True
    min_silence_duration_ms: int = 200
    vad_threshold: float = 0.3
    # Optional pre: Demucs vocal separation
    vocal_separation: bool = False
    # Optional post: wav2vec2 forced alignment
    align: bool = False


_STAGE_WEIGHTS = {"demucs": 3, "whisper": 5, "align": 1}


def _build_stage_list(options: TranscribeOptions) -> list[str]:
    stages: list[str] = []
    if options.vocal_separation:
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
    model_manager,
    ffmpeg_path: str,
    whisper,
    demucs=None,
    alignment_engine=None,
    on_progress: Optional[Callable[[float, str], None]] = None,
):
    """[Demucs] -> Whisper -> [align]. Returns faster-whisper TranscribeResult.

    Wrapper instances are passed in by the caller (DI-injected) instead of
    pulled from module-level singletons. `demucs` is required when
    `options.vocal_separation` is True; `alignment_engine` when
    `options.align` is True. Callers that don't use those features may
    pass None.

    Caller is responsible for: audio extraction from video source (use
    FFmpegWrapper.extract_audio_sync), output file writing, translation,
    and temp file lifecycle of the input audio_path itself. Demucs-separated
    vocals temp file is managed internally.
    """
    stages = _build_stage_list(options)
    stage_progress = _make_stage_progress(stages, on_progress)

    temp_vocals: Optional[Path] = None

    try:
        # Stage 1: Demucs vocal separation (optional)
        working_audio = audio_path
        if options.vocal_separation:
            if demucs is None:
                raise ValueError("demucs wrapper required when vocal_separation=True")
            import soundfile as sf

            stage_progress("demucs", 0.0, "task.progress.separating_vocals")
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
                if alignment_engine is None:
                    raise ValueError("alignment_engine wrapper required when align=True")
                aligner = alignment_engine
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
