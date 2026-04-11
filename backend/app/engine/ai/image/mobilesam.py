"""
MobileSAM object segmentation module.
Inherits PackageRuntime, provides image object segmentation (for AI object removal).
"""
from __future__ import annotations

import logging
from typing import Optional, Callable, Any

import numpy as np
import torch

from app.engine.ai.runtime.package import PackageRuntime
from app.engine.ai.registry import SLOT_SEGMENT

logger = logging.getLogger(__name__)


class MobileSAMWrapper(PackageRuntime):
    """
    MobileSAM object segmentation wrapper (inherits PackageRuntime).

    Responsibilities:
    1. Load MobileSAM model
    2. Provide SamPredictor for box-based segmentation
    """

    def __init__(self):
        super().__init__(slot=SLOT_SEGMENT)
        logger.info("MobileSAMWrapper initialized (PackageRuntime)")

    def _create_model(
        self,
        model_path: Any,
        config: dict,
        device: str,
        on_progress: Optional[Callable[[float, str], None]] = None,
    ) -> Any:
        """Load MobileSAM model."""
        if on_progress:
            on_progress(0.3, "task.progress.loading_mobilesam")

        from mobile_sam import sam_model_registry

        sam = sam_model_registry["vit_t"](checkpoint=str(model_path))
        sam.to(torch.device(device))
        sam.eval()

        logger.info(f"MobileSAM loaded on {device}")
        return sam

    def _resolve_model_path(self, model_id: str, variant: Optional[str] = None):
        """Resolve MobileSAM model path."""
        model_path = self._manager.get_model_path(model_id, variant or "default")
        if not model_path:
            from app.init.configs import SETTINGS
            model_path = SETTINGS.path.models / "mobilesam" / "mobile_sam.pt"
            if not model_path.exists():
                raise FileNotFoundError(
                    "MobileSAM model not downloaded. Please download it from Settings > Model Management."
                )

        config = {
            "model_id": model_id,
            "variant": variant or "default",
        }
        return model_path, config

    def predict_box(
        self,
        image_rgb: np.ndarray,
        box: np.ndarray,
        on_progress: Optional[Callable[[float, str], None]] = None,
    ) -> np.ndarray:
        """
        Predict object mask using a bounding box.

        Args:
            image_rgb: RGB image (H, W, 3) numpy array.
            box: [x1, y1, x2, y2] bounding box.

        Returns:
            Mask (H, W) uint8 numpy array (0 or 255).
        """
        with self.acquire(
            model_id="mobilesam",
            variant="default",
            on_progress=on_progress,
        ) as sam:
            from mobile_sam import SamPredictor

            predictor = SamPredictor(sam)
            predictor.set_image(image_rgb)

            masks, _, _ = predictor.predict(
                box=box.astype(np.float32),
                multimask_output=False,
            )
            return (masks[0] * 255).astype(np.uint8)


# ═══════════════════════════════════════════════════════════
# Singleton factory
# ═══════════════════════════════════════════════════════════
_mobilesam: Optional[MobileSAMWrapper] = None


def get_mobilesam() -> MobileSAMWrapper:
    """Get the MobileSAMWrapper singleton."""
    global _mobilesam
    if _mobilesam is None:
        _mobilesam = MobileSAMWrapper()
    return _mobilesam
