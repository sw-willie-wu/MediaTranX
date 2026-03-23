"""
語言與翻譯選項服務
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
包裝 app.utils.prompts 的語言/風格常數查詢，提供給 Route 層使用。
Route 不應直接 import app.utils.prompts 的常數。
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
    """語言與翻譯選項查詢服務（單例）"""

    _instance: Optional["LanguageService"] = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        logger.info("LanguageService initialized")

    def get_whisper_languages(self) -> list[dict]:
        """取得 Whisper 語言選項列表"""
        return WHISPER_LANGUAGE_OPTIONS

    def get_supported_languages(self) -> list[dict]:
        """取得支援的目標語言列表"""
        return SUPPORTED_LANGUAGES

    def get_translate_styles(self) -> list[dict]:
        """取得翻譯風格選項列表"""
        return STYLE_OPTIONS

    def get_whisper_to_bcp47(self) -> dict[str, str]:
        """取得 Whisper 語言代碼到 BCP 47 的映射"""
        return WHISPER_TO_BCP47

    def get_default_vlm_model(self) -> str:
        """取得預設 VLM 模型名稱"""
        return DEFAULT_VLM_MODEL

    def get_lang_names_en(self) -> dict[str, str]:
        """取得語言代碼到英文名稱的映射"""
        return LANG_NAMES_EN

    def get_model_status(self, model_id: str = "translategemma", model_size: str = "4b", quantization: Optional[str] = None) -> dict:
        """查詢翻譯模型狀態（llama-server 二進位 + 模型檔案）"""
        from app.engine.ai.model_manager import get_model_manager

        available = get_model_manager().is_llama_ready()
        variant = f"{model_size}:{quantization}" if quantization else model_size
        model_downloaded = (
            get_model_manager().get_model_path(model_id, variant) is not None
        )

        return {
            "available": available,
            "model_size": model_size,
            "model_downloaded": model_downloaded,
        }

    def get_vlm_status(self, model_id: str = "qwen3vl", size: str = "4b", quantization: Optional[str] = None) -> dict:
        """查詢 VLM 模型狀態"""
        from app.engine.ai.model_manager import get_model_manager

        available = get_model_manager().is_llama_ready()
        variant = f"{size}:{quantization}" if quantization else size
        model_downloaded = (
            get_model_manager().get_model_path(model_id, variant) is not None
        )

        return {
            "available": available,
            "model_id": model_id,
            "size": size,
            "model_downloaded": model_downloaded,
        }


_language_service: Optional[LanguageService] = None


def get_language_service() -> LanguageService:
    """取得 LanguageService 單例"""
    global _language_service
    if _language_service is None:
        _language_service = LanguageService()
    return _language_service
