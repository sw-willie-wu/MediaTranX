from .model_manager import (
    ModelManager,
    get_model_manager,
)
from .registry import (
    SLOT_WHISPER,
    SLOT_LLM,
    SLOT_PTH,
)
from .whisper import (
    WhisperWrapper,
    get_whisper,
    TranscribeSegment,
    TranscribeResult,
)
from .translate import (
    BaseTranslator,
    TranslateResult,
    SUPPORTED_LANGUAGES,
    WHISPER_TO_BCP47,
    get_translator,
    get_translategemma,
    get_qwen3,
    TranslateGemmaWrapper,
    Qwen3Wrapper,
)

__all__ = [
    "ModelManager", "get_model_manager",
    "SLOT_WHISPER", "SLOT_LLM", "SLOT_PTH",
    "WhisperWrapper", "get_whisper", "TranscribeSegment", "TranscribeResult",
    "BaseTranslator", "TranslateResult", "SUPPORTED_LANGUAGES", "WHISPER_TO_BCP47",
    "get_translator", "get_translategemma", "get_qwen3",
    "TranslateGemmaWrapper", "Qwen3Wrapper",
    # upscale: import lazily via backend.core.ai.upscale
]

