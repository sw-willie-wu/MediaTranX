from .base import BaseUpscaler
from .realesrgan import RealESRGANWrapper, get_realesrgan


def get_upscaler(model_id: str) -> BaseUpscaler:
    """根據 model_id 取得對應的超解析 wrapper"""
    # 之後加 hat、swinir、waifu2x 時在此擴充
    return get_realesrgan()


__all__ = [
    "get_upscaler",
    "get_realesrgan",
    "BaseUpscaler",
    "RealESRGANWrapper",
]
