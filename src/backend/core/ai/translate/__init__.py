from .base import BaseTranslator, TranslateResult, SUPPORTED_LANGUAGES, WHISPER_TO_BCP47
from .gemma import TranslateGemmaWrapper, get_translategemma
from .qwen3 import Qwen3Wrapper, get_qwen3


def get_translator(model_type: str = "translategemma") -> BaseTranslator:
    """根據 model_type 取得對應的翻譯模型 wrapper"""
    if model_type == "qwen3":
        return get_qwen3()
    return get_translategemma()


__all__ = [
    "get_translator",
    "get_translategemma",
    "get_qwen3",
    "BaseTranslator",
    "TranslateResult",
    "SUPPORTED_LANGUAGES",
    "WHISPER_TO_BCP47",
    "TranslateGemmaWrapper",
    "Qwen3Wrapper",
]
