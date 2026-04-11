"""
Language and translation options service.
Wraps language/style constant queries from app.utils.prompts for the route layer.
Routes should not import app.utils.prompts constants directly.
"""
import logging
from typing import Optional

from app.utils.prompts import (
    WHISPER_LANGUAGE_OPTIONS,
    SUPPORTED_LANGUAGES,
    STYLE_OPTIONS,
    WHISPER_TO_BCP47,
    LANG_NAMES_EN,
    DEFAULT_VLM_MODEL,
)

logger = logging.getLogger(__name__)


class LanguageService:
    """Language options, translation model status, and VLM status query service."""

    def __init__(self):
        logger.info("LanguageService initialized")

    def get_whisper_languages(self) -> list[dict]:
        """Get Whisper language options list."""
        return WHISPER_LANGUAGE_OPTIONS

    def get_supported_languages(self) -> list[dict]:
        """Get list of supported target languages."""
        return SUPPORTED_LANGUAGES

    def get_translate_styles(self) -> list[dict]:
        """Get list of translation style options."""
        return STYLE_OPTIONS

    def get_whisper_to_bcp47(self) -> dict[str, str]:
        """Get Whisper language code to BCP 47 mapping."""
        return WHISPER_TO_BCP47

    def get_default_vlm_model(self) -> str:
        """Get default VLM model name."""
        return DEFAULT_VLM_MODEL

    def get_lang_names_en(self) -> dict[str, str]:
        """Get language code to English name mapping."""
        return LANG_NAMES_EN

    def get_model_status(self, model_id: str = "translategemma", model_size: str = "4b", quantization: Optional[str] = None) -> dict:
        """Query translation model status (llama-server binary + model file)."""
        from app.init.container import get_container

        mm = get_container().model_manager()
        available = mm.is_llama_ready()
        variant = f"{model_size}:{quantization}" if quantization else model_size
        model_downloaded = (
            mm.get_model_path(model_id, variant) is not None
        )

        return {
            "available": available,
            "model_size": model_size,
            "model_downloaded": model_downloaded,
        }

    def get_vlm_status(self, model_id: str = "qwen3vl", size: str = "4b", quantization: Optional[str] = None) -> dict:
        """Query VLM model status."""
        from app.init.container import get_container

        mm = get_container().model_manager()
        available = mm.is_llama_ready()
        variant = f"{size}:{quantization}" if quantization else size
        model_downloaded = (
            mm.get_model_path(model_id, variant) is not None
        )

        return {
            "available": available,
            "model_id": model_id,
            "size": size,
            "model_downloaded": model_downloaded,
        }
