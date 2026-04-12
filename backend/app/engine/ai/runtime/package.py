"""
PackageRuntime - package-managed model executor.
Handles models whose loading is managed by third-party packages (e.g. Whisper, Demucs).
"""
import logging
from abc import abstractmethod
from typing import Optional, Callable, Any

import torch

from .base import BaseRuntime

logger = logging.getLogger(__name__)


class PackageRuntime(BaseRuntime):
    """
    Package-managed executor.

    For cases where model loading logic is handled by third-party packages (e.g. faster-whisper, demucs).
    Subclasses only need to implement _create_model() and _cleanup_model().

    Features:
    1. Automatic device selection (CUDA/CPU)
    2. Unified unload + CUDA cache cleanup
    3. Overridable _cleanup_model() for custom cleanup (e.g. Windows crash protection)
    """

    def __init__(self, slot: str):
        super().__init__(slot)
        self._device: Optional[str] = None

    @abstractmethod
    def _create_model(
        self,
        model_path: Any,
        config: dict,
        device: str,
        on_progress: Optional[Callable[[float, str], None]] = None,
    ) -> Any:
        """
        Subclass implementation: create model object.

        Args:
            model_path: Model path (directory or file).
            config: Model configuration dict.
            device: Compute device ("cuda" / "cpu").
            on_progress: Progress callback.

        Returns:
            Model object.
        """
        pass

    def _load_model_impl(
        self,
        model_path: Any,
        config: dict,
        on_progress: Optional[Callable[[float, str], None]] = None,
    ) -> Any:
        """Load model (unified device selection + delegate to _create_model)."""
        device = self._select_device(config.get("device"))
        self._device = device

        if on_progress:
            on_progress(0.1, "task.progress.preparing_model")

        model = self._create_model(model_path, config, device, on_progress)

        logger.info(f"PackageRuntime model loaded on {device}")
        return model

    def _unload_model_impl(self) -> None:
        """Unload model: call subclass cleanup logic first, then clear CUDA cache."""
        if self._model is not None:
            logger.info(f"Unloading package model from slot: {self._slot}")
            self._cleanup_model()

            if self._device and "cuda" in self._device:
                try:
                    torch.cuda.empty_cache()
                    logger.info("CUDA cache cleared")
                except Exception as e:
                    logger.warning(f"Failed to clear CUDA cache: {e}")

    def _cleanup_model(self) -> None:
        """
        Subclass override: custom cleanup logic.

        E.g. Whisper needs zombie protection, Demucs does not.
        Default: no-op.
        """
        pass

    def _select_device(self, preferred: Optional[str] = None) -> str:
        """
        Select compute device.

        Priority:
        1. preferred (if specified)
        2. CUDA (if available)
        3. CPU (fallback)
        """
        if preferred:
            return preferred

        try:
            if torch.cuda.is_available():
                return "cuda"
        except Exception:
            pass

        logger.info("No GPU acceleration available, using CPU")
        return "cpu"
