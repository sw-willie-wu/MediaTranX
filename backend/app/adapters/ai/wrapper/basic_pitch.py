"""
Basic Pitch wrapper -- audio-to-MIDI (non-drum tracks).
Inherits PackageWrapper, uses Spotify basic-pitch (TFLite/ONNX, CPU-only)
to convert audio to MIDI note events.
"""
from __future__ import annotations

import logging
import shutil
import tempfile
from pathlib import Path
from typing import Any, Callable, Optional

from app.adapters.ai.wrapper.base import PackageWrapper
from app.adapters.ai.registry import FORMAT_PKG, MODELS_REGISTRY, SLOT_BASIC_PITCH

logger = logging.getLogger(__name__)


class BasicPitchWrapper(PackageWrapper):
    """
    Basic Pitch audio-to-MIDI wrapper (inherits PackageWrapper).

    Responsibilities:
    1. Convert non-drum audio tracks to MIDI note events
    2. Model managed by the basic-pitch package itself
    3. CPU-only, no GPU required
    """

    def __init__(self):
        super().__init__(slot=SLOT_BASIC_PITCH)
        logger.info("BasicPitchWrapper initialized (PackageWrapper)")

    def _create_model(
        self,
        model_path: Any,
        config: dict,
        device: str,
        on_progress: Optional[Callable[[float, str], None]] = None,
    ) -> Any:
        """Load basic-pitch predict function and built-in ONNX model path."""
        # basic-pitch 0.4.x calls scipy.signal.gaussian which was removed in
        # scipy >= 1.13 (moved to scipy.signal.windows.gaussian). Patch the
        # attribute back before basic_pitch.inference imports note_creation,
        # otherwise AttributeError at first predict() call. Upstream issue:
        # https://github.com/spotify/basic-pitch/issues/199
        import scipy.signal as _scipy_signal
        if not hasattr(_scipy_signal, "gaussian"):
            from scipy.signal import windows as _scipy_windows
            _scipy_signal.gaussian = _scipy_windows.gaussian

        # Lazy import: importing the basic_pitch package runs backend detection
        # in its __init__ that hard-crashes (NameError) when onnxruntime can't
        # load. Keeping it out of module top level means a broken onnxruntime
        # only fails this feature, not backend startup (init_container).
        from basic_pitch import ICASSP_2022_MODEL_PATH
        from basic_pitch.inference import predict

        if on_progress:
            on_progress(0.3, "task.progress.loading_basicpitch")

        logger.info(f"Basic Pitch loaded: model={ICASSP_2022_MODEL_PATH}")
        return {"predict": predict, "model_path": ICASSP_2022_MODEL_PATH}

    def _resolve_model_path(self, model_id: str, variant, manager):
        """
        Resolve Basic Pitch model path.

        basic-pitch manages its own model (built-in TFLite/ONNX), returns None.
        """
        family = MODELS_REGISTRY[FORMAT_PKG].get(model_id)
        if not family:
            raise ValueError(f"Unknown PKG model: {model_id}")

        variant = variant or "default"
        variant_spec = family["variants"].get(variant)
        if not variant_spec:
            raise ValueError(f"Unknown variant '{variant}' for {model_id}")

        config = {
            "model_id": model_id,
            "variant": variant,
            "model_name": variant_spec.get("model_name", variant),
            "vram_mb": variant_spec.get("vram_mb", 0),
        }

        # basic-pitch manages model paths internally, return None
        return None, config

    def get_model_status(self) -> dict:
        """Check whether the basic-pitch package is available."""
        try:
            from basic_pitch.inference import predict  # noqa: F401
            available = True
        except (ImportError, ModuleNotFoundError):
            available = False

        return {
            "available": available,
            "model_downloaded": available,  # model is built into the package
        }

    def audio_to_midi(
        self,
        audio_path: str,
        onset_threshold: float = 0.3,
        frame_threshold: float = 0.15,
        minimum_note_length: float = 80.0,
        on_progress: Optional[Callable[[float, str], None]] = None,
    ) -> dict:
        """
        Convert audio to MIDI note events.

        Args:
            audio_path: Input audio path.
            onset_threshold: Onset detection threshold (default 0.3, basic-pitch default 0.5).
            frame_threshold: Frame detection threshold (default 0.15, basic-pitch default 0.3).
            minimum_note_length: Minimum note length in ms (default 80, basic-pitch default 127.7).
            on_progress: Progress callback.

        Returns:
            Track dict: {"name": ..., "instrument": 0, "is_drum": False, "notes": [...]}.
            Each note: {"pitch": int, "start": float, "duration": float, "velocity": int}.
        """
        if on_progress:
            on_progress(0.0, "task.progress.preparing_midi")

        # basic-pitch internally uses print/logging to output paths;
        # non-ASCII filenames crash on Windows cp950 console encoding.
        # Copy to an ASCII-safe temp path before processing.
        src = Path(audio_path)
        safe_path: str = str(src)
        tmp_dir = None
        try:
            src.name.encode("ascii")
        except UnicodeEncodeError:
            tmp_dir = tempfile.mkdtemp(prefix="bp_")
            safe_name = f"input{src.suffix}"
            safe_file = Path(tmp_dir) / safe_name
            shutil.copy2(src, safe_file)
            safe_path = str(safe_file)
            logger.debug("Copied non-ASCII path to temp: %s", safe_path)

        try:
            with self.acquire(
                model_id="basic_pitch",
                variant="default",
                on_progress=on_progress,
            ):
                # `acquire()` yields the wrapper itself (per BaseWrapper.acquire
                # contract); the loaded model dict lives on `self._model`.
                if on_progress:
                    on_progress(0.3, "task.progress.analyzing_audio")

                bp = self._model  # {"predict": fn, "model_path": Path}
                # predict(audio_path, model_or_model_path) returns (model_output, midi_data, note_events)
                model_output, midi_data, note_events = bp["predict"](
                    safe_path,
                    bp["model_path"],
                    onset_threshold=onset_threshold,
                    frame_threshold=frame_threshold,
                    minimum_note_length=minimum_note_length,
                )

                if on_progress:
                    on_progress(0.8, "task.progress.converting_midi")
        finally:
            if tmp_dir:
                shutil.rmtree(tmp_dir, ignore_errors=True)

        # Get stem name from audio path
        stem_name = Path(audio_path).stem

        # Convert note_events to standard format
        # note_events is a list of tuples: (start_time_s, end_time_s, pitch_midi, amplitude, bends)
        notes = []
        for event in note_events:
            start_s, end_s, pitch, amplitude = event[0], event[1], event[2], event[3]
            velocity = int(min(127, max(1, amplitude * 127)))
            duration = end_s - start_s
            notes.append({
                "pitch": int(pitch),
                "start": float(start_s),
                "duration": float(duration),
                "velocity": velocity,
            })

        if on_progress:
            on_progress(1.0, "task.progress.midi_complete")

        logger.info(f"Basic Pitch: {len(notes)} notes extracted from {stem_name}")

        return {
            "name": stem_name,
            "instrument": 0,
            "is_drum": False,
            "notes": notes,
        }
