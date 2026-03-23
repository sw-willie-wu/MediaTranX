"""
image - PTH 模型集合（超解析 + 人臉修復）
"""
from app.engine.ai.runtime.pth import PTHRuntime

# Upscale wrappers
from .realesrgan import RealESRGANWrapper, get_realesrgan
from .swinir import SwinIRWrapper, get_swinir
from .bsrgan import BSRGANWrapper, get_bsrgan
from .real_cugan import RealCUGANWrapper, get_real_cugan
from .waifu2x import Waifu2xWrapper, get_waifu2x

# Face restore wrappers
from .codeformer import CodeFormerWrapper, get_codeformer
from .gfpgan import GFPGANWrapper, get_gfpgan


def get_upscaler(model_id: str) -> PTHRuntime:
    """
    根據 model_id 取得對應的超解析 wrapper

    Args:
        model_id: 模型家族 ID（realesrgan/swinir/bsrgan/real-cugan/waifu2x）

    Returns:
        對應的 wrapper 實例
    """
    model_map = {
        "realesrgan": get_realesrgan,
        "swinir": get_swinir,
        "bsrgan": get_bsrgan,
        "real-cugan": get_real_cugan,
        "waifu2x": get_waifu2x,
    }

    factory = model_map.get(model_id)
    if not factory:
        raise ValueError(f"Unknown upscale model: {model_id}. Available: {list(model_map.keys())}")

    return factory()


def get_face_restorer(model_id: str):
    """
    根據 model_id 取得對應的人臉修復 wrapper

    Args:
        model_id: 模型家族 ID（codeformer/gfpgan）

    Returns:
        對應的 wrapper 實例
    """
    model_map = {
        "codeformer": get_codeformer,
        "gfpgan": get_gfpgan,
    }

    factory = model_map.get(model_id)
    if not factory:
        raise ValueError(f"Unknown face_restore model: {model_id}. Available: {list(model_map.keys())}")

    return factory()


__all__ = [
    "get_upscaler",
    "get_face_restorer",
    "get_realesrgan",
    "get_swinir",
    "get_bsrgan",
    "get_real_cugan",
    "get_waifu2x",
    "get_codeformer",
    "get_gfpgan",
    "RealESRGANWrapper",
    "SwinIRWrapper",
    "BSRGANWrapper",
    "RealCUGANWrapper",
    "Waifu2xWrapper",
    "CodeFormerWrapper",
    "GFPGANWrapper",
]
