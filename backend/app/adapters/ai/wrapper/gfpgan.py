"""
GFPGAN face restoration wrapper (Three-Layer Architecture V3).
Refactored: inherits PthWrapper, supports GAN enhancement.
"""
from __future__ import annotations

import logging
from typing import Any, Optional, Callable

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
        self._face_pipeline: Optional[Any] = None
        logger.info("GFPGANWrapper initialized (PthWrapper)")
    
    def restore(
        self,
        image: Image.Image,
        model_id: str = "v1.4",
        upscale: int = 2,
        on_progress: Optional[Callable[[float, str], None]] = None,
    ) -> Image.Image:
        """Run GFPGAN face restoration.

        Pipeline: detect faces → align each to 512x512 → GFPGAN restore →
        paste back. Background outside detected faces is unchanged.
        """
        variant_spec = MODELS_REGISTRY[FORMAT_PTH]["gfpgan"]["variants"].get(model_id)
        if not variant_spec:
            raise ValueError(f"Unknown GFPGAN variant: {model_id}")

        vram_needed = variant_spec["vram_mb"]  # noqa: F841 — used by outer mm.acquire (Wave D)

        with self.acquire(
            model_id="gfpgan",
            variant=model_id,
            on_progress=lambda p, m: on_progress(p * 0.05, m) if on_progress else None,
        ) as model:
            if self._face_pipeline is None:
                from app.adapters.ai.face_pipeline import FacePipeline
                self._face_pipeline = FacePipeline(device=self._device)

            def restore_fn(face_tensor):
                with torch.no_grad():
                    # IMPLEMENTER NOTE: GFPGAN's spandrel-wrapped call typically returns
                    # a tuple (restored_face, intermediate_features) or just the tensor.
                    # Unpack if tuple; pass through if tensor.
                    output = model(face_tensor)
                    if isinstance(output, tuple):
                        output = output[0]
                    return output

            face_progress = lambda p, m: on_progress(0.05 + p * 0.95, m) if on_progress else None
            return self._face_pipeline.restore(
                image, restore_fn, face_upscale=upscale, on_progress=face_progress,
            )
