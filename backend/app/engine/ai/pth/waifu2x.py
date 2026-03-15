"""
Waifu2x 動漫風格超解析封裝 (Three-Layer Architecture V3)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
繼承 PTHRuntime + Spandrel，支援 CUNet art 模型
"""
import logging
from typing import Optional, Callable

import numpy as np
from PIL import Image

from app.engine.ai.base import PTHRuntime
from app.engine.ai.registry import FORMAT_PTH, MODELS_REGISTRY, SLOT_PTH

logger = logging.getLogger(__name__)


class Waifu2xWrapper(PTHRuntime):
    """
    Waifu2x 動漫風格超解析封裝

    特性：
    1. 針對動漫/二次元影像優化
    2. CUNet art 模型，固定 2x 放大
    3. 透過 Spandrel 載入
    """

    def __init__(self):
        super().__init__(slot="waifu2x", use_spandrel=True)
        logger.info("Waifu2xWrapper initialized (PTHRuntime + Spandrel)")

    def enhance(
        self,
        image: Image.Image,
        model_id: str = "cunet",
        scale: int = 2,  # noqa: ARG002
        on_progress: Optional[Callable[[float, str], None]] = None,
    ) -> Image.Image:
        """
        執行 Waifu2x 超解析推理

        Args:
            image: 輸入影像
            model_id: 模型變體（cunet）
            scale: 放大倍數（固定 2）
            on_progress: 進度回調

        Returns:
            增強後的影像
        """
        variant_spec = MODELS_REGISTRY[FORMAT_PTH]["waifu2x"]["variants"].get(model_id)
        if not variant_spec:
            raise ValueError(f"Unknown Waifu2x variant: {model_id}")

        vram_needed = variant_spec["vram_mb"]
        self._manager.acquire(SLOT_PTH, required_vram_mb=vram_needed)

        try:
            with self.acquire(
                model_id="waifu2x",
                variant=model_id,
                on_progress=on_progress,
            ) as model:
                import torch
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


# ═══════════════════════════════════════════════════════════
# 單例工廠函數
# ═══════════════════════════════════════════════════════════
_waifu2x: Optional[Waifu2xWrapper] = None


def get_waifu2x() -> Waifu2xWrapper:
    """取得 Waifu2xWrapper 單例"""
    global _waifu2x
    if _waifu2x is None:
        _waifu2x = Waifu2xWrapper()
    return _waifu2x
