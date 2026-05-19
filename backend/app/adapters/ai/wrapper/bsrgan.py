"""
BSRGAN blind super-resolution wrapper (Three-Layer Architecture V3).
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


class BSRGANWrapper(PthWrapper):
    """
    BSRGAN blind super-resolution wrapper.

    Features:
    1. Targets real-world degraded images
    2. 4x super-resolution
    3. Uses Spandrel for automatic architecture detection
    """
    
    def __init__(self):
        super().__init__(slot="upscale", use_spandrel=True)
        logger.info("BSRGANWrapper initialized (PthWrapper + Spandrel)")
    
    def enhance(
        self,
        image: Image.Image,
        model_id: str = "default",
        scale: int = 4,  # noqa: ARG002
        on_progress: Optional[Callable[[float, str], None]] = None,
    ) -> Image.Image:
        """
        Run BSRGAN super-resolution inference.

        Args:
            image: Input image.
            model_id: Model variant (currently only "default").
            scale: Scale factor (fixed at 4).
            on_progress: Progress callback.

        Returns:
            Enhanced image.
        """
        # Get VRAM requirement
        variant_spec = MODELS_REGISTRY[FORMAT_PTH]["bsrgan"]["variants"].get(model_id)
        if not variant_spec:
            raise ValueError(f"Unknown BSRGAN variant: {model_id}")
        
        vram_needed = variant_spec["vram_mb"]  # noqa: F841 — used by outer mm.acquire (Wave D)

        # Load model using PthWrapper; ModelManager handles unload on eviction.
        with self.acquire(
            model_id="bsrgan",
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
            return Image.fromarray(output_array)
