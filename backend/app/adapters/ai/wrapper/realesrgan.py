"""
Real-ESRGAN super-resolution inference wrapper (Three-Layer Architecture V3).
Refactored: inherits PthWrapper, supports CUDA/CPU auto-switching and DirectML reservation.
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


class RealESRGANWrapper(PthWrapper):
    """
    Real-ESRGAN super-resolution wrapper (inherits PthWrapper).

    Responsibilities:
    1. Image super-resolution inference (2x/4x)
    2. Tile processing (large image chunking)
    3. Device auto-switching handled by PthWrapper
    """

    def __init__(self):
        super().__init__(slot="upscale", use_spandrel=True)
        logger.info("RealESRGANWrapper initialized (PthWrapper, spandrel)")
    
    def enhance(
        self,
        image: Image.Image,
        model_id: str = "x4plus",
        scale: int = 4,
        on_progress: Optional[Callable[[float, str], None]] = None,
    ) -> Image.Image:
        """
        Run super-resolution inference.

        Args:
            image: Input image.
            model_id: Model variant (x2plus/x4plus/x4plus-anime).
            scale: Scale factor.
            on_progress: Progress callback.

        Returns:
            Enhanced image.
        """
        # Get VRAM requirement and acquire lock
        variant_spec = MODELS_REGISTRY[FORMAT_PTH]["realesrgan"]["variants"].get(model_id)
        if not variant_spec:
            raise ValueError(f"Unknown RealESRGAN variant: {model_id}")
        
        vram_needed = variant_spec["vram_mb"]  # noqa: F841 — used by outer mm.acquire (Wave D)

        with self.acquire(
            model_id="realesrgan",
            variant=model_id,
            on_progress=on_progress
        ):
            img_array = np.array(image.convert("RGB"))
            img_tensor = torch.from_numpy(img_array).permute(2, 0, 1).unsqueeze(0).float() / 255.0
            img_tensor = img_tensor.to(self._device)

            def infer_cb(p: float, m: str) -> None:
                if on_progress:
                    on_progress(1.0 + p, m)

            output_tensor = self.run_inference(self._model, img_tensor, scale=scale, on_progress=infer_cb)
            output_array = (output_tensor.squeeze(0).permute(1, 2, 0).cpu().numpy() * 255.0).clip(0, 255).astype(np.uint8)
            result = Image.fromarray(output_array)

            # Release GPU tensors to avoid OOM during batch processing
            del img_tensor, output_tensor
            torch.cuda.empty_cache()

            return result
