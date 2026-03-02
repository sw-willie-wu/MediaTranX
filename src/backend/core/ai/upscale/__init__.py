from backend.core.ai.base import PTHRuntime
from .realesrgan import RealESRGANWrapper, get_realesrgan
from .swinir import SwinIRWrapper, get_swinir
from .bsrgan import BSRGANWrapper, get_bsrgan
from .real_cugan import RealCUGANWrapper, get_real_cugan


def get_upscaler(model_id: str) -> PTHRuntime:
    """
    根據 model_id 取得對應的超解析 wrapper
    
    Args:
        model_id: 模型家族 ID（realesrgan/swinir/bsrgan/real-cugan）
        
    Returns:
        對應的 wrapper 實例
    """
    model_map = {
        "realesrgan": get_realesrgan,
        "swinir": get_swinir,
        "bsrgan": get_bsrgan,
        "real-cugan": get_real_cugan,
    }
    
    factory = model_map.get(model_id)
    if not factory:
        raise ValueError(f"Unknown upscale model: {model_id}. Available: {list(model_map.keys())}")
    
    return factory()


__all__ = [
    "get_upscaler",
    "get_realesrgan",
    "get_swinir",
    "get_bsrgan",
    "get_real_cugan",
    "RealESRGANWrapper",
    "SwinIRWrapper",
    "BSRGANWrapper",
    "RealCUGANWrapper",
]
