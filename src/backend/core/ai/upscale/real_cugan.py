"""
Real-CUGAN 動漫風格超解析封裝 (Three-Layer Architecture V3)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
重構：繼承 PTHRuntime，支援多種去噪等級與放大倍數
"""
import logging
from typing import Optional, Callable

import numpy as np
from PIL import Image

from backend.core.ai.base import PTHRuntime
from backend.core.ai.registry import FORMAT_PTH, MODELS_REGISTRY, SLOT_PTH

logger = logging.getLogger(__name__)


class RealCUGANWrapper(PTHRuntime):
    """
    Real-CUGAN 動漫風格超解析封裝
    
    特性：
    1. 針對動漫/二次元影像優化
    2. 支援 2x/3x/4x 放大
    3. 可選去噪等級（-1/0/3）
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
        執行 Real-CUGAN 超解析推理
        
        Args:
            image: 輸入影像
            model_id: 模型變體（up2x-*/up3x-*/up4x-*）
            scale: 放大倍數（2/3/4）
            on_progress: 進度回調
            
        Returns:
            增強後的影像
        """
        # 獲取 VRAM 需求
        variant_spec = MODELS_REGISTRY[FORMAT_PTH]["real-cugan"]["variants"].get(model_id)
        if not variant_spec:
            raise ValueError(f"Unknown Real-CUGAN variant: {model_id}")
        
        vram_needed = variant_spec["vram_mb"]
        self._manager.acquire(SLOT_PTH, required_vram_mb=vram_needed)
        
        try:
            # 使用 PTHRuntime 載入模型
            with self.acquire(
                model_id="real-cugan",
                variant=model_id,
                on_progress=on_progress
            ) as model:
                import torch
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
# 單例工廠函數
# ═══════════════════════════════════════════════════════════
_real_cugan: Optional[RealCUGANWrapper] = None

def get_real_cugan() -> RealCUGANWrapper:
    """取得 RealCUGANWrapper 單例"""
    global _real_cugan
    if _real_cugan is None:
        _real_cugan = RealCUGANWrapper()
    return _real_cugan
