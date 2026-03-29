"""
MobileSAM 物件分割模組
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
繼承 PackageRuntime，提供圖片物件分割功能（用於 AI 移除物件）。
"""
from __future__ import annotations

import logging
from typing import Optional, Callable, Any

import numpy as np

from app.engine.ai.runtime.package import PackageRuntime
from app.engine.ai.registry import SLOT_SEGMENT

logger = logging.getLogger(__name__)


class MobileSAMWrapper(PackageRuntime):
    """
    MobileSAM 物件分割封裝（繼承 PackageRuntime）

    職責：
    1. 載入 MobileSAM 模型
    2. 提供 SamPredictor 用於 box-based 分割
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
        """載入 MobileSAM 模型"""
        if on_progress:
            on_progress(0.3, "載入 MobileSAM...")

        from mobile_sam import sam_model_registry
        import torch

        sam = sam_model_registry["vit_t"](checkpoint=str(model_path))
        sam.to(torch.device(device))
        sam.eval()

        logger.info(f"MobileSAM loaded on {device}")
        return sam

    def _resolve_model_path(self, model_id: str, variant: Optional[str] = None):
        """解析 MobileSAM 模型路徑"""
        model_path = self._manager.get_model_path(model_id, variant or "default")
        if not model_path:
            from app.engine.paths import get_models_dir
            model_path = get_models_dir("mobilesam") / "mobile_sam.pt"
            if not model_path.exists():
                raise FileNotFoundError(
                    "MobileSAM 模型未下載，請至設定 → 模型管理下載"
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
        用 bounding box 預測物件遮罩

        Args:
            image_rgb: RGB 圖片 (H, W, 3) numpy array
            box: [x1, y1, x2, y2] bounding box

        Returns:
            遮罩 (H, W) uint8 numpy array (0 or 255)
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
# 單例工廠函數
# ═══════════════════════════════════════════════════════════
_mobilesam: Optional[MobileSAMWrapper] = None


def get_mobilesam() -> MobileSAMWrapper:
    """取得 MobileSAMWrapper 單例"""
    global _mobilesam
    if _mobilesam is None:
        _mobilesam = MobileSAMWrapper()
    return _mobilesam
