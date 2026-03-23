"""
語言與翻譯選項服務
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
包裝 engine.ai.base.translate 的語言/風格常數查詢，提供給 Route 層使用。
Route 不應直接 import engine.ai.base.translate 的常數。
"""
import logging
from typing import Optional

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
        from app.engine.ai.llama.translate import WHISPER_LANGUAGE_OPTIONS
        return WHISPER_LANGUAGE_OPTIONS

    def get_supported_languages(self) -> list[dict]:
        """取得支援的目標語言列表"""
        from app.engine.ai.llama.translate import SUPPORTED_LANGUAGES
        return SUPPORTED_LANGUAGES

    def get_translate_styles(self) -> list[dict]:
        """取得翻譯風格選項列表"""
        from app.engine.ai.llama.translate import STYLE_OPTIONS
        return STYLE_OPTIONS

    def get_whisper_to_bcp47(self) -> dict[str, str]:
        """取得 Whisper 語言代碼到 BCP 47 的映射"""
        from app.engine.ai.llama.translate import WHISPER_TO_BCP47
        return WHISPER_TO_BCP47

    def get_default_vlm_model(self) -> str:
        """取得預設 VLM 模型名稱"""
        from app.engine.ai.llama.vlm import DEFAULT_VLM_MODEL
        return DEFAULT_VLM_MODEL

    def get_lang_names_en(self) -> dict[str, str]:
        """取得語言代碼到英文名稱的映射"""
        from app.engine.ai.llama.translate import LANG_NAMES_EN
        return LANG_NAMES_EN

    def get_translator(self, model_type: str = "translategemma"):
        """取得翻譯器實例（支援 translategemma / qwen3）"""
        from app.engine.ai.llama import get_translator
        return get_translator(model_type)


_language_service: Optional[LanguageService] = None


def get_language_service() -> LanguageService:
    """取得 LanguageService 單例"""
    global _language_service
    if _language_service is None:
        _language_service = LanguageService()
    return _language_service
