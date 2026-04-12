"""
PTHRuntime - PyTorch format executor.
Handles image processing model loading (e.g. Real-ESRGAN, SwinIR).
"""
import logging
from pathlib import Path
from typing import Optional, Callable, Any

import torch
import torch.nn.functional as F

from .base import BaseRuntime

logger = logging.getLogger(__name__)


class PTHRuntime(BaseRuntime):
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
    
    def _load_model_impl(
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
        """Tiled inference to avoid OOM on large images, with progress callback support."""
        import math

        _, _, h, w = img_tensor.shape
        tiles_x = math.ceil(w / tile_size)
        tiles_y = math.ceil(h / tile_size)
        total = tiles_x * tiles_y

        output = None
        actual_scale = scale  # Initial: use requested scale; corrected after first tile output

        for iy in range(tiles_y):
            for ix in range(tiles_x):
                x1, x2 = ix * tile_size, min((ix + 1) * tile_size, w)
                y1, y2 = iy * tile_size, min((iy + 1) * tile_size, h)
                x1p = max(x1 - tile_pad, 0)
                x2p = min(x2 + tile_pad, w)
                y1p = max(y1 - tile_pad, 0)
                y2p = min(y2 + tile_pad, h)

                tile = img_tensor[:, :, y1p:y2p, x1p:x2p]
                with torch.no_grad():
                    tile_out = model(tile)

                # Detect actual scale from first tile output (guard against model/request scale mismatch)
                if output is None:
                    actual_scale = tile_out.shape[3] // (x2p - x1p)
                    output = img_tensor.new_zeros(
                        (img_tensor.shape[0], img_tensor.shape[1], h * actual_scale, w * actual_scale)
                    )

                ox1 = (x1 - x1p) * actual_scale
                ox2 = ox1 + (x2 - x1) * actual_scale
                oy1 = (y1 - y1p) * actual_scale
                oy2 = oy1 + (y2 - y1) * actual_scale
                output[
                    :, :, y1 * actual_scale:y2 * actual_scale, x1 * actual_scale:x2 * actual_scale
                ] = tile_out[:, :, oy1:oy2, ox1:ox2]

                done = iy * tiles_x + ix + 1
                if on_progress:
                    on_progress(done / total, f"task.progress.tile_inference|{done}|{total}")

        return output

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
    
    def _unload_model_impl(self) -> None:
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
    
    def _resolve_model_path(self, model_id: str, variant: Optional[str] = None):
        """
        Resolve PTH format model path.

        PTH format characteristics:
        - Single .pth file
        - May have multiple variants (e.g. x2plus, x4plus)
        """
        from app.engine.ai.registry import FORMAT_PTH, MODELS_REGISTRY
        
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
        model_path = self._manager.get_model_path(model_id, variant)
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
