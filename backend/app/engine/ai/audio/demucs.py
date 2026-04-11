"""
Demucs audio source separation module.
Inherits PackageRuntime, uses the demucs package for 6-stem source separation
(vocals, drums, bass, guitar, piano, other).
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional, Callable, List, Dict, Any

import torch

from app.engine.ai.runtime.package import PackageRuntime
from app.engine.ai.registry import FORMAT_PKG, MODELS_REGISTRY, SLOT_DEMUCS

logger = logging.getLogger(__name__)


class DemucsWrapper(PackageRuntime):
    """
    Demucs audio source separation wrapper (inherits PackageRuntime).

    Responsibilities:
    1. 6-stem source separation (vocals, drums, bass, guitar, piano, other)
    2. Model loading managed by the demucs package itself
    3. Device auto-switching handled by PackageRuntime
    """

    def __init__(self):
        super().__init__(slot=SLOT_DEMUCS)
        logger.info("DemucsWrapper initialized (PackageRuntime)")

    def _create_model(
        self,
        model_path: Any,
        config: dict,
        device: str,
        on_progress: Optional[Callable[[float, str], None]] = None,
    ) -> Any:
        """Load model using demucs.api.Separator."""
        import functools
        from demucs.api import Separator
        from app.init.configs import SETTINGS

        if on_progress:
            on_progress(0.3, "task.progress.loading_demucs")

        model_name = config.get("model_name", "htdemucs_6s")

        # Point torch hub cache to models/demucs/ for unified checkpoint storage
        models_dir = SETTINGS.path.models
        models_dir.mkdir(parents=True, exist_ok=True)
        hub_dir = str(models_dir / SLOT_DEMUCS)
        original_hub_dir = torch.hub.get_dir()
        torch.hub.set_dir(hub_dir)

        # PyTorch 2.6+ defaults to weights_only=True; demucs checkpoints require weights_only=False
        _original_load = torch.load
        torch.load = functools.partial(_original_load, weights_only=False)
        try:
            separator = Separator(
                model=model_name,
                device=device,
                shifts=1,
                overlap=0.25,
            )
        finally:
            torch.load = _original_load
            torch.hub.set_dir(original_hub_dir)

        logger.info(f"Demucs Separator loaded: {model_name} on {device}")
        return separator

    def _resolve_model_path(self, model_id: str, variant: Optional[str] = None):
        """
        Resolve Demucs model path.

        Demucs models are downloaded by the package to a repo directory;
        returns models/demucs/ as the repo directory.
        """
        family = MODELS_REGISTRY[FORMAT_PKG].get(model_id)
        if not family:
            raise ValueError(f"Unknown PKG model: {model_id}")

        variant_spec = family["variants"].get(variant)
        if not variant_spec:
            raise ValueError(f"Unknown variant '{variant}' for {model_id}")

        config = {
            "model_id": model_id,
            "variant": variant,
            "model_name": variant_spec.get("model_name", variant),
            "vram_mb": variant_spec.get("vram_mb", 2000),
            "sources": variant_spec.get("sources", []),
        }

        # demucs manages model paths internally (torch hub cache), return None
        return None, config

    def get_model_status(self, variant: str = "htdemucs_6s") -> dict:
        """Check model availability (demucs package + checkpoint in torch hub cache)."""
        family = MODELS_REGISTRY[FORMAT_PKG].get("demucs")
        if not family:
            return {"available": False, "model_downloaded": False}

        variant_spec = family["variants"].get(variant)
        if not variant_spec:
            return {"available": False, "model_downloaded": False}

        # Check if demucs package is installed
        try:
            from demucs.api import Separator  # noqa: F401
            available = True
        except (ImportError, ModuleNotFoundError):
            available = False

        # Check if models/demucs/checkpoints/ has model checkpoint
        model_downloaded = False
        try:
            from app.init.configs import SETTINGS
            checkpoints_dir = SETTINGS.path.models / SLOT_DEMUCS / "checkpoints"
            if checkpoints_dir.exists():
                model_downloaded = any(f.suffix == ".th" for f in checkpoints_dir.iterdir())
        except Exception:
            pass

        return {
            "available": available,
            "model_downloaded": model_downloaded,
        }

    def separate(
        self,
        audio_path: str,
        variant: str = "htdemucs_6s",
        stems: Optional[List[str]] = None,
        on_progress: Optional[Callable[[float, str], None]] = None,
    ) -> tuple[Dict[str, Any], int]:
        """
        Execute audio source separation.

        Args:
            audio_path: Input audio path.
            variant: Model variant.
            stems: Stem names to separate (None=all).
            on_progress: Progress callback.

        Returns:
            ({stem_name: tensor}, sample_rate)
        """
        family = MODELS_REGISTRY[FORMAT_PKG]["demucs"]
        variant_spec = family["variants"][variant]
        all_sources = variant_spec["sources"]

        if on_progress:
            on_progress(0.0, "task.progress.preparing_separation")

        with self.acquire(
            model_id="demucs",
            variant=variant,
            on_progress=on_progress,
        ) as separator:
            if on_progress:
                on_progress(0.3, "task.progress.separating")

            # Set callback for progress reporting during inference (used for cancel check)
            if on_progress:
                def _progress_callback(state: dict):
                    # Demucs callback is called after each segment inference
                    # Calling on_progress triggers TaskManager's cancel check
                    on_progress(0.5, "task.progress.separating")
                separator._callback = _progress_callback

            # Separator.separate_audio_file handles: read, resample, segment, infer
            origin, separated = separator.separate_audio_file(audio_path)

            sample_rate = separator.samplerate

            if on_progress:
                on_progress(0.9, "task.progress.processing_results")

        # Filter specified stems
        result = {}
        for source_name in all_sources:
            if stems and source_name not in stems:
                continue
            if source_name in separated:
                result[source_name] = separated[source_name].cpu()

        if on_progress:
            on_progress(1.0, "task.progress.separation_done")

        return result, sample_rate


# ═══════════════════════════════════════════════════════════
# Singleton factory
# ═══════════════════════════════════════════════════════════
_demucs: Optional[DemucsWrapper] = None


def get_demucs() -> DemucsWrapper:
    """Get the DemucsWrapper singleton."""
    global _demucs
    if _demucs is None:
        _demucs = DemucsWrapper()
    return _demucs
