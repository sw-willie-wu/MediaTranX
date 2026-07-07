"""Wrapper base classes — pure model executor wrappers.

This module consolidates the three base classes used by concrete wrappers:

- ``BaseWrapper``: abstract base. Model API only; lifecycle and orchestration
  (acquire / load / unload coordination) are owned by ModelManager. Does NOT
  reference the DI container.
- ``PackageWrapper``: base for models whose loading is managed by third-party
  packages (e.g. faster-whisper, demucs). Handles device selection + unified
  cleanup.
- ``PthWrapper``: base for .pth PyTorch checkpoint models (e.g. Real-ESRGAN,
  SwinIR). Handles Spandrel/torch loading + smart tiled inference.
"""
import logging
import threading
from abc import ABC, abstractmethod
from contextlib import contextmanager
from pathlib import Path
from typing import Optional, Callable, Any

import torch
import torch.nn.functional as F

logger = logging.getLogger(__name__)


class BaseWrapper(ABC):
    """Model executor base class.

    Responsibilities:
    1. Concrete model load / unload (subclass implements `_load_impl` / `_unload_impl`)
    2. Thread-safe state (one model loaded at a time per instance)

    NOT responsible for:
    - VRAM lock coordination (ModelManager does this)
    - Acquire lifecycle / context manager (ModelManager does this)
    """

    def __init__(self, slot: str):
        self.slot = slot                              # public attribute
        self._lock = threading.RLock()               # impl detail
        self._model: Optional[Any] = None            # hidden, read via is_loaded()
        self._current_config: Optional[dict] = None  # hidden, read via get_current_config()
        self._model_manager = None                   # set by ModelManager at registration
        logger.debug(f"BaseWrapper initialized for slot: {slot}")

    # -- Public API (called by ModelManager) --

    def load(
        self,
        model_path: Any,
        config: dict,
        on_progress: Optional[Callable[[float, str], None]] = None,
    ) -> None:
        """Load model. Called by ModelManager inside its acquire()."""
        with self._lock:
            if self._model is not None:
                self._unload_impl()
            self._model = self._load_impl(model_path, config, on_progress)
            self._current_config = config

    def unload(self) -> None:
        """Unload model. Called by ModelManager on evict / shutdown."""
        with self._lock:
            if self._model is not None:
                self._unload_impl()
                self._model = None
                self._current_config = None

    @contextmanager
    def acquire(
        self,
        model_id: str,
        variant: Optional[str] = None,
        on_progress: Optional[Callable[[float, str], None]] = None,
        gate_class: str = "task",
    ):
        """Acquire this wrapper loaded with the requested model/variant.

        Thin bridge to `ModelManager.acquire(self.slot, ...)`. Yields whatever
        the manager yields (typically `self` for non-dispatcher slots; the
        currently-dispatched wrapper for dispatcher slots). The wrapper must
        have been registered with a ModelManager — typically done by
        `init_container` calling `register_runtime_provider` / `register_dispatcher`
        / `register_runtime`.
        """
        if self._model_manager is None:
            raise RuntimeError(
                f"{type(self).__name__}(slot={self.slot!r}) not registered with "
                "ModelManager; cannot acquire (DI wiring missing or test setup incomplete)"
            )
        with self._model_manager.acquire(
            slot=self.slot, model_id=model_id, variant=variant, on_progress=on_progress,
            gate_class=gate_class,
        ) as runtime:
            yield runtime

    def is_loaded(self) -> bool:
        return self._model is not None

    def get_current_config(self) -> Optional[dict]:
        return self._current_config.copy() if self._current_config else None

    # -- Subclass override hooks --

    @abstractmethod
    def _load_impl(
        self,
        model_path: Any,
        config: dict,
        on_progress: Optional[Callable[[float, str], None]] = None,
    ) -> Any:
        """Subclass: concrete model loading. Returns loaded model object."""
        ...

    @abstractmethod
    def _unload_impl(self) -> None:
        """Subclass: concrete model unloading (cleanup, zombie protection, etc.)."""
        ...

    # -- Optional override (for subclasses that build richer configs) --

    def _resolve_model_path(self, model_id, variant, manager):
        """Default: delegate path/config lookup to the ModelManager passed in.

        Called by `ModelManager.acquire` which injects `self` as `manager`.
        Subclasses that need richer config (e.g. LlmWrapper assembling
        mmproj paths) override with the same signature.
        """
        path = manager.get_model_path(model_id, variant)
        config = manager.get_model_config(model_id, variant) or {}
        config.setdefault("model_id", model_id)
        config.setdefault("variant", variant)
        return path, config


class PackageWrapper(BaseWrapper):
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

    def _load_impl(
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

        logger.info(f"PackageWrapper model loaded on {device}")
        return model

    def _unload_impl(self) -> None:
        """Unload model: call subclass cleanup logic first, then clear CUDA cache."""
        if self._model is not None:
            logger.info(f"Unloading package model from slot: {self.slot}")
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


class PthWrapper(BaseWrapper):
    """
    PTH executor (based on PyTorch / Spandrel).

    Features:
    1. Single weight file (.pth)
    2. CUDA/CPU auto-switching
    3. DirectML support interface reserved
    4. Optional Spandrel universal loader
    """

    def __init__(self, slot: str, use_spandrel: bool = True):
        """
        Args:
            slot: Model slot.
            use_spandrel: Whether to use Spandrel universal architecture loader.
        """
        super().__init__(slot)
        self._use_spandrel = use_spandrel
        self._device = None

    def _load_impl(
        self,
        model_path: Path,
        config: dict,
        on_progress: Optional[Callable[[float, str], None]] = None
    ) -> Any:
        """
        Load PTH model.

        Args:
            model_path: .pth file path.
            config: Config dict (contains arch, device, etc.).

        Returns:
            PyTorch model instance.
        """
        if on_progress:
            on_progress(0.2, "task.progress.init_pytorch")

        # Device selection logic
        device = self._select_device(config.get("device"))
        self._device = device

        if on_progress:
            on_progress(0.4, f"task.progress.loading_weights|{device}")

        if self._use_spandrel:
            model = self._load_with_spandrel(model_path, device, config)
        else:
            model = self._load_with_torch(model_path, device, config)

        logger.info(f"PTH model loaded: {model_path.name} on {device}")
        return model

    def _load_with_spandrel(self, model_path: Path, device: str, config: dict) -> Any:
        """Load using Spandrel universal loader (automatic architecture detection)."""
        try:
            # basicsr (the sole consumer of torchvision's removed functional_tensor
            # module) may be pulled by a spandrel arch load. Ensure the compat shim
            # is in place BEFORE importing spandrel. Lazy + idempotent — keeps
            # torchvision off the bind path (see app/init/compat.py).
            from app.init.compat import ensure_torchvision_functional_tensor_compat
            ensure_torchvision_functional_tensor_compat()
            import spandrel
            model = spandrel.ModelLoader().load_from_file(str(model_path))
            model = model.to(device)
            model.eval()
            logger.info(f"Loaded via Spandrel: {type(model).__name__}")
            return model
        except ImportError:
            logger.warning("Spandrel not available, falling back to torch.load")
            return self._load_with_torch(model_path, device, config)

    def _load_with_torch(self, model_path: Path, device: str, config: dict) -> Any:
        """Load using native PyTorch (subclass must provide architecture)."""
        state_dict = torch.load(str(model_path), map_location=device)

        # Some models (e.g. Real-ESRGAN) wrap weights under params_ema / params
        if "params_ema" in state_dict:
            state_dict = state_dict["params_ema"]
        elif "params" in state_dict:
            state_dict = state_dict["params"]

        # Subclass must override _build_arch() to provide model architecture
        if hasattr(self, '_build_arch'):
            model = self._build_arch(config)
            model.load_state_dict(state_dict, strict=True)
            model = model.to(device)
            model.eval()
            return model
        else:
            raise NotImplementedError(
                "Subclass must implement _build_arch() or enable use_spandrel=True"
            )

    def _get_max_pixels(self) -> int:
        """Dynamically determine max pixels for non-tiled inference based on free VRAM."""
        try:
            if not torch.cuda.is_available():
                return 256 * 256
            free_vram, _ = torch.cuda.mem_get_info()
            free_gb = free_vram / 1024 ** 3
            if free_gb >= 8:   return 1024 * 1024
            if free_gb >= 5:   return 768 * 768
            if free_gb >= 3:   return 512 * 512
            if free_gb >= 1.5: return 256 * 256
            return 128 * 128
        except Exception:
            return 256 * 256

    def _get_tile_size(self) -> int:
        """Tile chunk size (edge length used for actual chunking)."""
        max_px = self._get_max_pixels()
        return int(max_px ** 0.5)

    def _tile_inference(
        self,
        model,
        img_tensor,
        scale: int,
        tile_size: int,
        tile_pad: int = 32,
        on_progress: Optional[Callable[[float, str], None]] = None,
    ):
        """Tiled inference — delegates to shared helper (pure tensor op)."""
        from app.adapters.ai.tile_inference import tile_inference_run
        return tile_inference_run(
            model=model,
            img_tensor=img_tensor,
            scale=scale,
            tile_size=tile_size,
            tile_pad=tile_pad,
            on_progress=on_progress,
        )

    def run_inference(
        self,
        model,
        img_tensor,
        scale: int = 4,
        on_progress: Optional[Callable[[float, str], None]] = None,
    ):
        """Smart inference: auto-tile large images, process small images whole."""
        _, _, h, w = img_tensor.shape

        # Some models (e.g. x2plus) use pixel_unshuffle, requiring h/w to be multiples of 4
        pad_h = (4 - h % 4) % 4
        pad_w = (4 - w % 4) % 4
        if pad_h or pad_w:
            img_padded = F.pad(img_tensor, (0, pad_w, 0, pad_h), mode='reflect')
        else:
            img_padded = img_tensor

        max_pixels = self._get_max_pixels()
        tile_size = self._get_tile_size()
        if w * h > max_pixels:
            logger.info(f"Image {w}×{h} ({w*h} px) > max_pixels {max_pixels}, tiling with tile_size {tile_size}")
            result = self._tile_inference(model, img_padded, scale, tile_size, on_progress=on_progress)
        else:
            with torch.no_grad():
                result = model(img_padded)

        # Crop padding to restore original dimensions
        if pad_h or pad_w:
            out_scale = result.shape[2] // img_padded.shape[2]
            result = result[:, :, :h * out_scale, :w * out_scale]

        return result

    def _select_device(self, preferred_device: Optional[str] = None) -> str:
        """
        Select compute device (DirectML extension point reserved).

        Priority:
        1. preferred_device (if valid)
        2. CUDA (if available)
        3. DirectML (future extension)
        4. CPU (fallback)
        """
        if preferred_device:
            return preferred_device

        # CUDA detection
        try:
            if torch.cuda.is_available():
                return "cuda"
        except Exception:
            pass

        # DirectML detection (reserved)
        # if has_directml():
        #     return "dml"  # requires torch-directml or onnxruntime-directml

        logger.info("No GPU acceleration available, using CPU")
        return "cpu"

    def _unload_impl(self) -> None:
        """
        Unload PTH model.

        PyTorch models can be safely released, but CUDA cache needs to be cleared.
        """
        if self._model is not None:
            logger.info("Unloading PTH model")

            # Clear CUDA cache
            if self._device and "cuda" in self._device:
                try:
                    torch.cuda.empty_cache()
                    logger.info("CUDA cache cleared")
                except Exception as e:
                    logger.warning(f"Failed to clear CUDA cache: {e}")

    def _resolve_model_path(self, model_id: str, variant, manager):
        """
        Resolve PTH format model path.

        PTH format characteristics:
        - Single .pth file
        - May have multiple variants (e.g. x2plus, x4plus)
        """
        from app.adapters.ai.registry import FORMAT_PTH, MODELS_REGISTRY

        family = MODELS_REGISTRY[FORMAT_PTH].get(model_id)
        if not family:
            raise ValueError(f"Unknown PTH model: {model_id}")

        # Default to the first variant
        if not variant:
            variant = list(family["variants"].keys())[0]

        variant_spec = family["variants"].get(variant)
        if not variant_spec:
            raise ValueError(f"Unknown variant '{variant}' for {model_id}")

        # Download/validate via ModelManager
        model_path = manager.get_model_path(model_id, variant)
        if not model_path:
            # PTH format may be a local file (no repo_id)
            from app.init.configs import SETTINGS
            local_path = SETTINGS.path.models / family["slot"] / variant_spec["filename"]
            if local_path.exists():
                model_path = local_path
            else:
                raise FileNotFoundError(
                    f"Model not found: {model_id}/{variant}. "
                    f"Expected at: {local_path}"
                )

        config = {
            "model_id": model_id,
            "variant": variant,
            "filename": variant_spec.get("filename", ""),
            "vram_mb": variant_spec.get("vram_mb", 2000),
            "arch": variant_spec.get("arch"),
            "scale": variant_spec.get("scale", 4),
        }

        return model_path, config
