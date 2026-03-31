"""
Real-ESRGAN 超解析推理封裝 (Three-Layer Architecture V3)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
重構：繼承 PTHRuntime，支援 CUDA/CPU 自動切換與 DirectML 預留
"""
from __future__ import annotations

import logging
from typing import Optional, Callable

from app.engine.ai.runtime.pth import PTHRuntime
from app.engine.ai.registry import FORMAT_PTH, MODELS_REGISTRY, SLOT_PTH

logger = logging.getLogger(__name__)


class RealESRGANWrapper(PTHRuntime):
    """
    Real-ESRGAN 超解析封裝（繼承 PTHRuntime）
    
    職責：
    1. 影像超解析推理（2x/4x）
    2. Tile 處理（大圖分塊）
    3. 設備自動切換由 PTHRuntime 處理
    """
    
    def __init__(self):
        super().__init__(slot=SLOT_PTH, use_spandrel=True)
        logger.info("RealESRGANWrapper initialized (PTHRuntime, spandrel)")
    
    def enhance(
        self,
        image: Image.Image,
        model_id: str = "x4plus",
        scale: int = 4,
        on_progress: Optional[Callable[[float, str], None]] = None,
    ) -> Image.Image:
        """
        執行超解析推理
        
        Args:
            image: 輸入影像
            model_id: 模型變體（x2plus/x4plus/x4plus-anime）
            scale: 放大倍數
            on_progress: 進度回調
            
        Returns:
            增強後的影像
        """
        # 獲取 VRAM 需求並 acquire 鎖
        variant_spec = MODELS_REGISTRY[FORMAT_PTH]["realesrgan"]["variants"].get(model_id)
        if not variant_spec:
            raise ValueError(f"Unknown RealESRGAN variant: {model_id}")
        
        vram_needed = variant_spec["vram_mb"]
        self._manager.acquire(SLOT_PTH, required_vram_mb=vram_needed)
        
        with self.acquire(
            model_id="realesrgan",
            variant=model_id,
            on_progress=on_progress
        ) as model:
            import numpy as np
            from PIL import Image
            import torch
            img_array = np.array(image.convert("RGB"))
            img_tensor = torch.from_numpy(img_array).permute(2, 0, 1).unsqueeze(0).float() / 255.0
            img_tensor = img_tensor.to(self._device)

            def infer_cb(p: float, m: str) -> None:
                if on_progress:
                    on_progress(1.0 + p, m)

            output_tensor = self.run_inference(model, img_tensor, scale=scale, on_progress=infer_cb)
            output_array = (output_tensor.squeeze(0).permute(1, 2, 0).cpu().numpy() * 255.0).clip(0, 255).astype(np.uint8)
            result = Image.fromarray(output_array)

            # 釋放 GPU tensor，避免批次跑時 OOM
            del img_tensor, output_tensor
            torch.cuda.empty_cache()

            return result


# ═══════════════════════════════════════════════════════════
# 單例工廠函數（向後兼容）
# ═══════════════════════════════════════════════════════════
_realesrgan: Optional[RealESRGANWrapper] = None

def get_realesrgan() -> RealESRGANWrapper:
    """取得 RealESRGANWrapper 單例"""
    global _realesrgan
    if _realesrgan is None:
        _realesrgan = RealESRGANWrapper()
    return _realesrgan
