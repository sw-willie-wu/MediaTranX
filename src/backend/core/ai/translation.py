"""
翻譯模型分發器
根據 model_type 取得對應的翻譯模型 wrapper
"""


def get_translator(model_type: str = "translategemma"):
    """取得翻譯模型 wrapper（TranslateGemma 或 Qwen3）"""
    if model_type == "qwen3":
        from .qwen3 import get_qwen3
        return get_qwen3()
    from .translategemma import get_translategemma
    return get_translategemma()
