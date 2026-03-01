"""
Real-ESRGAN 超解析推理封裝
"""
import logging
from typing import Optional, Callable

import numpy as np
from PIL import Image

from backend.core.ai.model_manager import get_model_manager
from backend.core.device import get_device
from .base import BaseUpscaler

logger = logging.getLogger(__name__)


class RealESRGANWrapper(BaseUpscaler):
    VRAM_MB = {
        "realesrgan-x4plus": 2000,
        "hat-l-x4":          4000,
    }

    def _load_model(self, model_id: str, on_progress: Optional[Callable] = None) -> None:
        model_path = get_model_manager().get_model_path("upscale", model_id)
        if not model_path:
            raise FileNotFoundError(f"模型未下載: {model_id}，請先至「AI 模組管理」下載")

        if on_progress:
            on_progress(0.3, "正在初始化模型架構...")

        from realesrgan import RealESRGANer
        from basicsr.archs.rrdbnet_arch import RRDBNet

        device = get_device()
        arch = RRDBNet(num_in_ch=3, num_out_ch=3, num_feat=64, num_block=23, num_grow_ch=32, scale=4)
        self._model = RealESRGANer(
            scale=4,
            model_path=str(model_path),
            model=arch,
            tile=400,
            tile_pad=10,
            pre_pad=0,
            half="cuda" in device,
            device=device,
        )
        self._current_model_id = model_id

        if on_progress:
            on_progress(1.0, "模型載入完成")
        logger.info(f"Loaded RealESRGAN: {model_id} on {device}")

    def _run_enhance(self, image: Image.Image, scale: int) -> Image.Image:
        img_bgr = np.array(image.convert("RGB"))[:, :, ::-1]
        output_bgr, _ = self._model.enhance(img_bgr, outscale=scale)
        return Image.fromarray(output_bgr[:, :, ::-1])


_realesrgan: Optional[RealESRGANWrapper] = None


def get_realesrgan() -> RealESRGANWrapper:
    global _realesrgan
    if _realesrgan is None:
        _realesrgan = RealESRGANWrapper()
    return _realesrgan
