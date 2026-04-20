"""
Waifu2x anime-style super-resolution wrapper (Three-Layer Architecture V3).
Inherits PthWrapper + Spandrel, supports CUNet art models.
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


class Waifu2xWrapper(PthWrapper):
    """
    Waifu2x anime-style super-resolution wrapper.

    Features:
    1. Optimized for anime/2D images
    2. CUNet art model, fixed 2x upscaling
    3. Loaded via Spandrel
    """

    def __init__(self):
        super().__init__(slot="waifu2x", use_spandrel=True)
        logger.info("Waifu2xWrapper initialized (PthWrapper + Spandrel)")

    def enhance(
        self,
        image: Image.Image,
        model_id: str = "cunet",
        scale: int = 2,  # noqa: ARG002
        on_progress: Optional[Callable[[float, str], None]] = None,
    ) -> Image.Image:
        """
        Run Waifu2x super-resolution inference.

        Args:
            image: Input image.
            model_id: Model variant (cunet).
            scale: Scale factor (fixed at 2).
            on_progress: Progress callback.

        Returns:
            Enhanced image.
        """
        variant_spec = MODELS_REGISTRY[FORMAT_PTH]["waifu2x"]["variants"].get(model_id)
        if not variant_spec:
            raise ValueError(f"Unknown Waifu2x variant: {model_id}")

        vram_needed = variant_spec["vram_mb"]  # noqa: F841 — used by outer mm.acquire (Wave D)

        try:
            with self.acquire(
                model_id="waifu2x",
                variant=model_id,
                on_progress=on_progress,
            ) as model:
                img_array = np.array(image.convert("RGB"))
                img_tensor = torch.from_numpy(img_array).permute(2, 0, 1).unsqueeze(0).float() / 255.0
                img_tensor = img_tensor.to(self._device)

                def infer_cb(p: float, m: str) -> None:
                    if on_progress:
                        on_progress(1.0 + p, m)

                output_tensor = self.run_inference(model, img_tensor, scale=2, on_progress=infer_cb)
                output_array = (output_tensor.squeeze(0).permute(1, 2, 0).cpu().numpy() * 255.0).clip(0, 255).astype(np.uint8)
                return Image.fromarray(output_array)

        finally:
            self._unload_model()
