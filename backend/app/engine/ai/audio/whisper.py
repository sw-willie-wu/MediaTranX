"""
Whisper speech recognition module.
Inherits PackageRuntime, uses faster-whisper for speech recognition.
Warning: Windows crash protection -- CTranslate2 destructor triggers crashes; zombie mechanism required.
"""
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional, Any

from faster_whisper import WhisperModel

from app.engine.ai.runtime.package import PackageRuntime
from app.engine.ai.registry import SLOT_WHISPER, FORMAT_PKG, MODELS_REGISTRY

logger = logging.getLogger(__name__)

# Critical protection mechanism: Windows stability safeguard
# CTranslate2's C++ destructor triggers STATUS_STACK_BUFFER_OVERRUN crashes on Windows
# Must keep Python references to unloaded models to prevent destructor execution
_zombie_models: list = []


@dataclass
class TranscribeWord:
    """An aligned word (only available after alignment)."""
    word: str
    start: float
    end: float
    score: float  # alignment confidence score

@dataclass
class TranscribeSegment:
    """A transcription segment."""
    start: float   # start time (seconds)
    end: float     # end time (seconds)
    text: str      # recognized text
    words: list[TranscribeWord] | None = None  # only available after alignment

@dataclass
class TranscribeResult:
    """Transcription result."""
    language: str                    # detected language
    language_probability: float      # language probability
    segments: list[TranscribeSegment]
    duration: float                  # total audio duration (seconds)


# ═══════════════════════════════════════════════════════════
# Word-level timestamps -> smart sentence splitting
# ═══════════════════════════════════════════════════════════
# Pause interval threshold (seconds): gap between consecutive words exceeding this is a split candidate
_PAUSE_THRESHOLD_S = 0.3
# Max characters per line: when exceeded and pause points exist, prefer splitting
_MAX_CHARS_PER_LINE = 42


def _split_by_words(words: list) -> list[TranscribeSegment]:
    """
    Smart sentence splitting using word-level timestamps.

    Strategy:
    1. Correct timestamps -- start/end taken from first/last word (removing VAD padding)
    2. Long sentence splitting -- cut at largest pause to keep each line reasonable
    3. Maintain semantic integrity -- no per-word splitting; translation gets complete phrases
    """
    if not words:
        return []

    # Find all candidate split points: pause gaps between words
    pause_points: list[tuple[int, float]] = []  # (index, gap_seconds)
    for i in range(1, len(words)):
        gap = words[i].start - words[i - 1].end
        if gap >= _PAUSE_THRESHOLD_S:
            pause_points.append((i, gap))

    # If sentence is short enough or no pause points, output as single segment with corrected timestamps
    total_text = "".join(w.word for w in words).strip()
    if not pause_points or len(total_text) <= _MAX_CHARS_PER_LINE:
        return [TranscribeSegment(
            start=words[0].start,
            end=words[-1].end,
            text=total_text,
        )]

    # Recursive splitting: cut at the largest pause each time
    result: list[TranscribeSegment] = []
    _recursive_split(words, pause_points, result)
    return result


def _recursive_split(
    words: list,
    pause_points: list[tuple[int, float]],
    result: list[TranscribeSegment],
) -> None:
    """Split at the largest pause; recursively split if sub-segments are too long."""
    text = "".join(w.word for w in words).strip()

    # Filter pause_points belonging to the current words range
    if not pause_points or len(text) <= _MAX_CHARS_PER_LINE:
        result.append(TranscribeSegment(
            start=words[0].start,
            end=words[-1].end,
            text=text,
        ))
        return

    # Find largest pause
    best = max(pause_points, key=lambda p: p[1])
    split_idx = best[0]

    left_words = words[:split_idx]
    right_words = words[split_idx:]
    left_pauses = [(i, g) for i, g in pause_points if i < split_idx]
    right_pauses = [(i - split_idx, g) for i, g in pause_points if i > split_idx]

    _recursive_split(left_words, left_pauses, result)
    _recursive_split(right_words, right_pauses, result)


class WhisperWrapper(PackageRuntime):
    """
    Whisper speech recognition wrapper (inherits PackageRuntime).

    Responsibilities:
    1. Transcription logic (speech -> text)
    2. Progress calculation and sentence splitting
    3. Windows crash protection handled via _cleanup_model()
    """

    def __init__(self):
        super().__init__(slot=SLOT_WHISPER)
        logger.info("WhisperWrapper initialized (PackageRuntime)")

    def _create_model(
        self,
        model_path: Any,
        config: dict,
        device: str,
        on_progress: Optional[Callable[[float, str], None]] = None,
    ) -> Any:
        """Load CTranslate2 model using faster-whisper."""
        if on_progress:
            on_progress(0.2, "task.progress.init_ctranslate2")

        from app.engine.device import get_compute_type

        compute_type = config.get("compute_type", get_compute_type())

        if on_progress:
            on_progress(0.5, f"task.progress.loading_model_device|{device}")

        model = WhisperModel(
            str(model_path),
            device=device,
            compute_type=compute_type,
        )

        logger.info(f"Whisper model loaded: {model_path} on {device}")
        return model

    def _cleanup_model(self) -> None:
        """
        Windows crash protection.

        Steps:
        1. Call unload_model() to release CUDA memory
        2. Add object to _zombie_models to prevent C++ destructor execution
        """
        if self._model is None:
            return

        # Step 1: Release CUDA memory
        try:
            if hasattr(self._model, 'model') and hasattr(self._model.model, 'unload_model'):
                self._model.model.unload_model()
                logger.info("CTranslate2 CUDA memory released via unload_model()")
        except Exception as e:
            logger.warning(f"CTranslate2 unload_model() failed: {e}")

        # Step 2: Zombify object (Windows crash protection)
        _zombie_models.append(self._model)
        logger.debug(f"Model zombified (total zombies: {len(_zombie_models)})")

    def _resolve_model_path(self, model_id: str, variant: Optional[str] = None):
        """
        Resolve Whisper model path.

        BIN/PKG format characteristics:
        - Is a directory (not a single file)
        - Downloaded as a complete snapshot from HuggingFace
        """
        family = MODELS_REGISTRY[FORMAT_PKG].get(model_id)
        if not family:
            raise ValueError(f"Unknown PKG model: {model_id}")

        size_config = family["variants"].get(variant)
        if not size_config:
            raise ValueError(f"Unknown variant '{variant}' for {model_id}")

        # Validate via ModelManager
        model_path = self._manager.get_model_path(model_id, variant)
        if not model_path:
            raise FileNotFoundError(
                f"Model not downloaded: {model_id}/{variant}. "
                f"Please download from HuggingFace: {size_config['repo_id']}"
            )

        config = {
            "model_id": model_id,
            "variant": variant,
            "repo_id": size_config["repo_id"],
            "vram_mb": size_config["vram_mb"],
        }

        return model_path, config

    def get_model_status(self, model_size: str = "medium") -> dict:
        """Query model status."""
        model_path = self._manager.get_model_path("whisper", model_size)

        from app.init.configs import SETTINGS
        venv_fw = SETTINGS.path.venv / "Lib" / "site-packages" / "faster_whisper"
        available = venv_fw.is_dir()

        return {
            "available": available,
            "model_size": model_size,
            "model_downloaded": model_path is not None,
        }

    async def download_only(self, model_size: str, on_progress=None) -> None:
        """Download model only, without loading into memory."""
        await self._manager.download_model("whisper", model_size, on_progress=on_progress)

    def transcribe(
        self,
        audio_path: str | Path,
        language: Optional[str] = None,
        model_size: str = "medium",
        on_progress: Optional[Callable[[float, str], None]] = None,
        word_timestamps: bool = False,
        condition_on_previous_text: bool = True,
        min_silence_duration_ms: int = 200,
        vad_threshold: float = 0.3,
    ) -> TranscribeResult:
        """
        Transcribe audio.

        Args:
            audio_path: Audio file path.
            language: Specify language (None for auto-detection).
            model_size: Model size (tiny/base/small/medium/large-v3).
            on_progress: Progress callback.
            word_timestamps: Whether to generate word-level timestamps.
            condition_on_previous_text: Whether to use previous text conditioning.
            min_silence_duration_ms: VAD minimum silence duration.
            vad_threshold: VAD threshold.

        Returns:
            TranscribeResult
        """
        audio_path = Path(audio_path)

        # Get VRAM requirement
        size_config = MODELS_REGISTRY[FORMAT_PKG]["whisper"]["variants"].get(model_size)
        if not size_config:
            raise ValueError(f"Unknown Whisper model size: {model_size}")

        vram_needed = size_config["vram_mb"]
        self._manager.acquire(SLOT_WHISPER, required_vram_mb=vram_needed)

        try:
            # Load model using PackageRuntime's acquire()
            if on_progress:
                on_progress(0.0, "task.progress.loading_whisper")

            with self.acquire(
                model_id="whisper",
                variant=model_size,
                on_progress=lambda p, m: on_progress(p * 0.05, m) if on_progress else None
            ) as model:
                if on_progress:
                    on_progress(0.05, "task.progress.start_recognition")

                # Execute transcription
                segments_gen, info = model.transcribe(
                    str(audio_path),
                    language=language,
                    beam_size=5,
                    word_timestamps=word_timestamps,
                    condition_on_previous_text=condition_on_previous_text,
                    vad_filter=True,
                    vad_parameters=dict(
                        min_silence_duration_ms=min_silence_duration_ms,
                        threshold=vad_threshold,
                    ),
                )

                # Collect segment results
                duration = info.duration
                segments: list[TranscribeSegment] = []
                for segment in segments_gen:
                    if word_timestamps and segment.words:
                        # Word-level timestamps: correct sentence boundaries with word times + smart long sentence splitting
                        sub_segs = _split_by_words(segment.words)
                        segments.extend(sub_segs)
                    else:
                        segments.append(TranscribeSegment(
                            start=segment.start,
                            end=segment.end,
                            text=segment.text.strip(),
                        ))
                    if on_progress and duration > 0:
                        progress = 0.05 + (segment.end / duration) * 0.95
                        on_progress(min(progress, 1.0), f"task.progress.recognizing_pct|{progress:.0%}")

                if on_progress:
                    on_progress(0.95, "task.progress.recognition_complete")

                # Convert Chinese output to Traditional Chinese
                detected_lang = info.language
                if detected_lang == "zh" or (language and language.startswith("zh")):
                    import opencc
                    converter = opencc.OpenCC('s2t')
                    for seg in segments:
                        seg.text = converter.convert(seg.text)

                result = TranscribeResult(
                    language=detected_lang,
                    language_probability=info.language_probability,
                    segments=segments,
                    duration=duration,
                )

            if on_progress:
                on_progress(1.0, "task.progress.recognition_complete")

            return result
        finally:
            # Unload model to release VRAM
            self._unload_model()


# ═══════════════════════════════════════════════════════════
# Singleton factory
# ═══════════════════════════════════════════════════════════
_whisper: Optional[WhisperWrapper] = None

def get_whisper() -> WhisperWrapper:
    """Get the WhisperWrapper singleton."""
    global _whisper
    if _whisper is None:
        _whisper = WhisperWrapper()
    return _whisper
