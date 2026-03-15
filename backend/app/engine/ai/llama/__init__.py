"""
llama 子套件 — 基於 llama-server 的翻譯與 VLM OCR 模組。
"""

from app.engine.ai.base.translate import (
    BaseTranslator,
    TranslateResult,
    SUPPORTED_LANGUAGES,
    WHISPER_TO_BCP47,
)
from .gemma import TranslateGemmaWrapper, get_translategemma
from .qwen3 import Qwen3Wrapper, get_qwen3
from .vlm import VlmOcrWrapper, get_vlm_ocr, DEFAULT_VLM_MODEL


def get_translator(model_type: str = "translategemma") -> BaseTranslator:
    """取得翻譯器實例（工廠函式）"""
    if model_type == "qwen3":
        return get_qwen3()
    return get_translategemma()


__all__ = [
    # translate
    "BaseTranslator",
    "TranslateResult",
    "SUPPORTED_LANGUAGES",
    "WHISPER_TO_BCP47",
    "get_translator",
    "get_translategemma",
    "get_qwen3",
    "TranslateGemmaWrapper",
    "Qwen3Wrapper",
    # vlm
    "VlmOcrWrapper",
    "get_vlm_ocr",
    "DEFAULT_VLM_MODEL",
]
