"""
face_restore - 人臉修復模型集合
"""
from .codeformer import CodeFormerWrapper, get_codeformer
from .gfpgan import GFPGANWrapper, get_gfpgan


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
    "get_face_restorer",
    "get_codeformer",
    "get_gfpgan",
    "CodeFormerWrapper",
    "GFPGANWrapper",
]
