"""
SwinIR Transformer 超解析封裝 (Three-Layer Architecture V3)
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


class SwinIRWrapper(PTHRuntime):
    """
    SwinIR Transformer 超解析封裝
    
    特性：
    1. 使用 Spandrel 自動識別架構
    2. 支援 Lightweight/Classical/RealWorld 三種模式
    3. 4x 超解析
    """
    
    def __init__(self):
        super().__init__(slot="swinir", use_spandrel=True)
        logger.info("SwinIRWrapper initialized (PTHRuntime + Spandrel)")
    
    def enhance(
        self,
        image: Image.Image,
        model_id: str = "realworld-x4",
        scale: int = 4,  # noqa: ARG002
        on_progress: Optional[Callable[[float, str], None]] = None,
    ) -> Image.Image:
        """
        執行 SwinIR 超解析推理
        
        Args:
            image: 輸入影像
            model_id: 模型變體（lightweight-x4/classical-x4/realworld-x4）
            scale: 放大倍數（固定為 4）
            on_progress: 進度回調
            
        Returns:
            增強後的影像
        """
        # 獲取 VRAM 需求
        variant_spec = MODELS_REGISTRY[FORMAT_PTH]["swinir"]["variants"].get(model_id)
        if not variant_spec:
            raise ValueError(f"Unknown SwinIR variant: {model_id}")
        
        vram_needed = variant_spec["vram_mb"]
        self._manager.acquire(SLOT_PTH, required_vram_mb=vram_needed)
        
        try:
            # 使用 PTHRuntime 載入模型
            with self.acquire(
                model_id="swinir",
                variant=model_id,
                on_progress=on_progress
            ) as model:
                # Spandrel 自動處理推理
                if hasattr(model, 'forward'):
                    # Spandrel ModelDescriptor
                    img_array = np.array(image.convert("RGB"))
                    img_tensor = self._image_to_tensor(img_array)
                    
                    output_tensor = model(img_tensor)  # type: ignore
                    output_array = self._tensor_to_image(output_tensor)
                    
                    return Image.fromarray(output_array)
                else:
                    # 直接是 PyTorch 模型
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
    
    def _image_to_tensor(self, image: np.ndarray):
        """將 numpy 影像轉為 tensor (C, H, W)"""
        import torch
        tensor = torch.from_numpy(image).permute(2, 0, 1).unsqueeze(0).float() / 255.0
        return tensor.to(self._device)
    
    def _tensor_to_image(self, tensor):
        """將 tensor 轉回 numpy 影像"""
        array = (tensor.squeeze(0).permute(1, 2, 0).cpu().numpy() * 255.0).clip(0, 255).astype(np.uint8)
        return array


# ═══════════════════════════════════════════════════════════
# 單例工廠函數
# ═══════════════════════════════════════════════════════════
_swinir: Optional[SwinIRWrapper] = None

def get_swinir() -> SwinIRWrapper:
    """取得 SwinIRWrapper 單例"""
    global _swinir
    if _swinir is None:
        _swinir = SwinIRWrapper()
    return _swinir
