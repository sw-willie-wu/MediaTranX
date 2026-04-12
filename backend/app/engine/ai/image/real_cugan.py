"""
Real-CUGAN anime-style super-resolution wrapper (Three-Layer Architecture V3).
Refactored: inherits PTHRuntime, supports multiple denoise levels and scale factors.
"""
from __future__ import annotations

import logging
from typing import Optional, Callable

import numpy as np
import torch
from PIL import Image

from app.engine.ai.runtime.pth import PTHRuntime
from app.engine.ai.registry import FORMAT_PTH, MODELS_REGISTRY, SLOT_PTH

logger = logging.getLogger(__name__)


class RealCUGANWrapper(PTHRuntime):
    """
    Real-CUGAN anime-style super-resolution wrapper.

    Features:
    1. Optimized for anime/2D images
    2. Supports 2x/3x/4x upscaling
    3. Configurable denoise levels (-1/0/3)
    """
    
    def __init__(self):
        super().__init__(slot="real-cugan", use_spandrel=True)
        logger.info("RealCUGANWrapper initialized (PTHRuntime + Spandrel)")
    
    def enhance(
        self,
        image: Image.Image,
        model_id: str = "up4x-conservative",
        scale: int = 4,  # noqa: ARG002
        on_progress: Optional[Callable[[float, str], None]] = None,
    ) -> Image.Image:
        """
        Run Real-CUGAN super-resolution inference.

        Args:
            image: Input image.
            model_id: Model variant (up2x-*/up3x-*/up4x-*).
            scale: Scale factor (2/3/4).
            on_progress: Progress callback.

        Returns:
            Enhanced image.
        """
        # Get VRAM requirement
        variant_spec = MODELS_REGISTRY[FORMAT_PTH]["real-cugan"]["variants"].get(model_id)
        if not variant_spec:
            raise ValueError(f"Unknown Real-CUGAN variant: {model_id}")
        
        vram_needed = variant_spec["vram_mb"]
        self._manager.acquire(SLOT_PTH, required_vram_mb=vram_needed)
        
        try:
            # Load model using PTHRuntime
            with self.acquire(
                model_id="real-cugan",
                variant=model_id,
                on_progress=on_progress
            ) as model:
                img_array = np.array(image.convert("RGB"))
                img_tensor = torch.from_numpy(img_array).permute(2, 0, 1).unsqueeze(0).float() / 255.0
                img_tensor = img_tensor.to(self._device)

                def infer_cb(p: float, m: str) -> None:
                    if on_progress:
                        on_progress(1.0 + p, m)

                output_tensor = self.run_inference(model, img_tensor, scale=scale, on_progress=infer_cb)
                output_array = (output_tensor.squeeze(0).permute(1, 2, 0).cpu().numpy() * 255.0).clip(0, 255).astype(np.uint8)
                return Image.fromarray(output_array)
        
        finally:
            self._unload_model()


# ═══════════════════════════════════════════════════════════
# Singleton factory
# ═══════════════════════════════════════════════════════════
_real_cugan: Optional[RealCUGANWrapper] = None

def get_real_cugan() -> RealCUGANWrapper:
    """Get the RealCUGANWrapper singleton."""
    global _real_cugan
    if _real_cugan is None:
        _real_cugan = RealCUGANWrapper()
    return _real_cugan
