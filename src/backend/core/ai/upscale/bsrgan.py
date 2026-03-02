"""
BSRGAN 盲超解析封裝 (Three-Layer Architecture V3)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
重構：繼承 PTHRuntime，支援 Spandrel 通用載入
"""
import logging
from typing import Optional, Callable

import numpy as np
from PIL import Image

from backend.core.ai.base import PTHRuntime
from backend.core.ai.registry import FORMAT_PTH, MODELS_REGISTRY, SLOT_PTH

logger = logging.getLogger(__name__)


class BSRGANWrapper(PTHRuntime):
    """
    BSRGAN 盲超解析封裝
    
    特性：
    1. 針對真實世界退化影像
    2. 4x 超解析
    3. 使用 Spandrel 自動識別架構
    """
    
    def __init__(self):
        super().__init__(slot="bsrgan", use_spandrel=True)
        logger.info("BSRGANWrapper initialized (PTHRuntime + Spandrel)")
    
    def enhance(
        self,
        image: Image.Image,
        model_id: str = "default",
        scale: int = 4,  # noqa: ARG002
        on_progress: Optional[Callable[[float, str], None]] = None,
    ) -> Image.Image:
        """
        執行 BSRGAN 超解析推理
        
        Args:
            image: 輸入影像
            model_id: 模型變體（目前僅 "default"）
            scale: 放大倍數（固定為 4）
            on_progress: 進度回調
            
        Returns:
            增強後的影像
        """
        # 獲取 VRAM 需求
        variant_spec = MODELS_REGISTRY[FORMAT_PTH]["bsrgan"]["variants"].get(model_id)
        if not variant_spec:
            raise ValueError(f"Unknown BSRGAN variant: {model_id}")
        
        vram_needed = variant_spec["vram_mb"]
        self._manager.acquire(SLOT_PTH, required_vram_mb=vram_needed)
        
        try:
            # 使用 PTHRuntime 載入模型
            with self.acquire(
                model_id="bsrgan",
                variant=model_id,
                on_progress=on_progress
            ) as model:
                # Spandrel 處理推理
                import torch
                img_array = np.array(image.convert("RGB"))
                img_tensor = torch.from_numpy(img_array).permute(2, 0, 1).unsqueeze(0).float() / 255.0
                img_tensor = img_tensor.to(self._device)
                
                with torch.no_grad():
                    output_tensor = model(img_tensor)  # type: ignore
                
                output_array = (output_tensor.squeeze(0).permute(1, 2, 0).cpu().numpy() * 255.0).clip(0, 255).astype(np.uint8)
                return Image.fromarray(output_array)
        
        finally:
            self._unload_model()


# ═══════════════════════════════════════════════════════════
# 單例工廠函數
# ═══════════════════════════════════════════════════════════
_bsrgan: Optional[BSRGANWrapper] = None

def get_bsrgan() -> BSRGANWrapper:
    """取得 BSRGANWrapper 單例"""
    global _bsrgan
    if _bsrgan is None:
        _bsrgan = BSRGANWrapper()
    return _bsrgan
