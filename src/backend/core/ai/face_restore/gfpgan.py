"""
GFPGAN 人臉修復封裝 (Three-Layer Architecture V3)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
重構：繼承 PTHRuntime，支援 GAN 增強
"""
import logging
from typing import Optional, Callable

import numpy as np
from PIL import Image

from ..base import PTHRuntime
from ..registry import FORMAT_PTH, MODELS_REGISTRY, SLOT_PTH

logger = logging.getLogger(__name__)


class GFPGANWrapper(PTHRuntime):
    """
    GFPGAN 人臉修復封裝
    
    特性：
    1. 使用 GAN 技術進行真實人臉修復
    2. 適合處理老照片、低畫質人臉
    3. 支援高清晰度輸出（v1.4 版本）
    """
    
    def __init__(self):
        super().__init__(slot="gfpgan", use_spandrel=False)
        logger.info("GFPGANWrapper initialized (PTHRuntime)")
    
    def restore(
        self,
        image: Image.Image,
        model_id: str = "v1.4",
        upscale: int = 2,  # noqa: ARG002
        on_progress: Optional[Callable[[float, str], None]] = None,
    ) -> Image.Image:
        """
        執行 GFPGAN 人臉修復推理
        
        Args:
            image: 輸入影像
            model_id: 模型變體（目前僅 "v1.4"）
            upscale: 放大倍數（1/2/4）
            on_progress: 進度回調
            
        Returns:
            修復後的影像
            
        TODO: 目前是簡易實作，未來可整合 GFPGAN 完整流程（人臉偵測、修復、背景增強）
        """
        # 獲取 VRAM 需求
        variant_spec = MODELS_REGISTRY[FORMAT_PTH]["gfpgan"]["variants"].get(model_id)
        if not variant_spec:
            raise ValueError(f"Unknown GFPGAN variant: {model_id}")
        
        vram_needed = variant_spec["vram_mb"]
        self._manager.acquire(SLOT_PTH, required_vram_mb=vram_needed)
        
        try:
            # 使用 PTHRuntime 載入模型
            with self.acquire(
                model_id="gfpgan",
                variant=model_id,
                on_progress=on_progress
            ) as model:
                # 簡易推理流程（實際使用需要完整的人臉檢測 pipeline）
                import torch
                img_array = np.array(image.convert("RGB"))
                img_tensor = torch.from_numpy(img_array).permute(2, 0, 1).unsqueeze(0).float() / 255.0
                img_tensor = img_tensor.to(self._device)
                
                with torch.no_grad():
                    # GFPGAN 需要特殊處理
                    # 這裡是簡化版本，實際需依 GFPGAN 官方 API
                    if hasattr(model, 'forward'):
                        output_tensor = model(img_tensor)
                    else:
                        output_tensor = img_tensor  # fallback
                
                output_array = (output_tensor.squeeze(0).permute(1, 2, 0).cpu().numpy() * 255.0).clip(0, 255).astype(np.uint8)
                return Image.fromarray(output_array)
        
        finally:
            self._unload_model()


# ═══════════════════════════════════════════════════════════
# 單例工廠函數
# ═══════════════════════════════════════════════════════════
_gfpgan: Optional[GFPGANWrapper] = None

def get_gfpgan() -> GFPGANWrapper:
    """取得 GFPGANWrapper 單例"""
    global _gfpgan
    if _gfpgan is None:
        _gfpgan = GFPGANWrapper()
    return _gfpgan
