"""
SwinIR Transformer super-resolution wrapper (Three-Layer Architecture V3).
Refactored: inherits PthWrapper, supports Spandrel universal loading.
"""
from __future__ import annotations

import logging
from typing import Optional, Callable

import numpy as np
import torch
from PIL import Image

from app.adapters.ai.wrapper.base import PthWrapper
from app.adapters.ai.registry import FORMAT_PTH, MODELS_REGISTRY

logger = logging.getLogger(__name__)


class SwinIRWrapper(PthWrapper):
    """
    SwinIR Transformer super-resolution wrapper.

    Features:
    1. Uses Spandrel for automatic architecture detection
    2. Supports Lightweight/Classical/RealWorld modes
    3. 4x super-resolution
    """

    def __init__(self):
        super().__init__(slot="swinir", use_spandrel=True)
        logger.info("SwinIRWrapper initialized (PthWrapper + Spandrel)")

    def _get_tile_size(self) -> int:
        """SwinIR Transformer attention is O(n^2), requires smaller tiles than CNN."""
        try:
            if not torch.cuda.is_available():
                return 128
            free_vram, _ = torch.cuda.mem_get_info()
            free_gb = free_vram / 1024 ** 3
            if free_gb >= 6:   return 512
            if free_gb >= 3:   return 256
            if free_gb >= 1.5: return 128
            return 64
        except Exception:
            return 128
    
    def enhance(
        self,
        image: Image.Image,
        model_id: str = "realworld-x4",
        scale: int = 4,  # noqa: ARG002
        on_progress: Optional[Callable[[float, str], None]] = None,
    ) -> Image.Image:
        """
        Run SwinIR super-resolution inference.

        Args:
            image: Input image.
            model_id: Model variant (lightweight-x4/classical-x4/realworld-x4).
            scale: Scale factor (fixed at 4).
            on_progress: Progress callback.

        Returns:
            Enhanced image.
        """
        # Get VRAM requirement
        variant_spec = MODELS_REGISTRY[FORMAT_PTH]["swinir"]["variants"].get(model_id)
        if not variant_spec:
            raise ValueError(f"Unknown SwinIR variant: {model_id}")
        
        vram_needed = variant_spec["vram_mb"]  # noqa: F841 — used by outer mm.acquire (Wave D)

        # Load model using PthWrapper; ModelManager handles unload on eviction.
        with self.acquire(
            model_id="swinir",
            variant=model_id,
            on_progress=on_progress
        ):
            img_array = np.array(image.convert("RGB"))
            img_tensor = self._image_to_tensor(img_array)

            def infer_cb(p: float, m: str) -> None:
                if on_progress:
                    on_progress(1.0 + p, m)

            output_tensor = self.run_inference(self._model, img_tensor, scale=scale, on_progress=infer_cb)
            output_array = self._tensor_to_image(output_tensor)
            return Image.fromarray(output_array)
    
    def _image_to_tensor(self, image: np.ndarray):
        """Convert numpy image to tensor (C, H, W)."""
        tensor = torch.from_numpy(image).permute(2, 0, 1).unsqueeze(0).float() / 255.0
        return tensor.to(self._device)
    
    def _tensor_to_image(self, tensor):
        """Convert tensor back to numpy image."""
        array = (tensor.squeeze(0).permute(1, 2, 0).cpu().numpy() * 255.0).clip(0, 255).astype(np.uint8)
        return array
