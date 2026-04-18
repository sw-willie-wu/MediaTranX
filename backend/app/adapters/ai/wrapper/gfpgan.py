"""
GFPGAN face restoration wrapper (Three-Layer Architecture V3).
Refactored: inherits PthWrapper, supports GAN enhancement.
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


class GFPGANWrapper(PthWrapper):
    """
    GFPGAN face restoration wrapper.

    Features:
    1. Uses GAN for realistic face restoration
    2. Suitable for old photos and low-quality face images
    3. Supports high-definition output (v1.4)
    """

    def __init__(self):
        super().__init__(slot="gfpgan", use_spandrel=True)
        logger.info("GFPGANWrapper initialized (PthWrapper)")
    
    def restore(
        self,
        image: Image.Image,
        model_id: str = "v1.4",
        upscale: int = 2,  # noqa: ARG002
        on_progress: Optional[Callable[[float, str], None]] = None,
    ) -> Image.Image:
        """
        Run GFPGAN face restoration inference.

        Args:
            image: Input image.
            model_id: Model variant (currently only "v1.4").
            upscale: Scale factor (1/2/4).
            on_progress: Progress callback.

        Returns:
            Restored image.

        TODO: Currently a simplified implementation; future integration with full GFPGAN
              pipeline (face detection, restoration, background enhancement).
        """
        # Get VRAM requirement
        variant_spec = MODELS_REGISTRY[FORMAT_PTH]["gfpgan"]["variants"].get(model_id)
        if not variant_spec:
            raise ValueError(f"Unknown GFPGAN variant: {model_id}")
        
        vram_needed = variant_spec["vram_mb"]  # noqa: F841 — used by outer mm.acquire (Wave D)

        try:
            # Load model using PthWrapper
            with self.acquire(
                model_id="gfpgan",
                variant=model_id,
                on_progress=on_progress
            ) as model:
                # Simplified inference (production use requires full face detection pipeline)
                img_array = np.array(image.convert("RGB"))
                img_tensor = torch.from_numpy(img_array).permute(2, 0, 1).unsqueeze(0).float() / 255.0
                img_tensor = img_tensor.to(self._device)
                
                with torch.no_grad():
                    # GFPGAN requires special handling
                    # This is a simplified version; actual use should follow the GFPGAN official API
                    if hasattr(model, 'forward'):
                        output_tensor = model(img_tensor)
                    else:
                        output_tensor = img_tensor  # fallback
                
                output_array = (output_tensor.squeeze(0).permute(1, 2, 0).cpu().numpy() * 255.0).clip(0, 255).astype(np.uint8)
                return Image.fromarray(output_array)
        
        finally:
            self._unload_model()


# ═══════════════════════════════════════════════════════════
# Singleton factory
# ═══════════════════════════════════════════════════════════
_gfpgan: Optional[GFPGANWrapper] = None

def get_gfpgan() -> GFPGANWrapper:
    """Get the GFPGANWrapper singleton."""
    global _gfpgan
    if _gfpgan is None:
        _gfpgan = GFPGANWrapper()
    return _gfpgan
