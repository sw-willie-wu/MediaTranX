"""
TranslateGemma 翻譯模組
使用 llama-cpp-python 載入 GGUF 量化模型，提供文字翻譯功能
模型不打包在 app 中，首次使用時自動從 HuggingFace 下載
"""
import logging
from pathlib import Path
from typing import Optional

from backend.core.paths import get_models_dir
from .model_manager import SLOT_TRANSLATEGEMMA
from .base_translator import (
    BaseTranslator,
    TranslateResult,
    WHISPER_TO_BCP47,
    SUPPORTED_LANGUAGES,
    LANG_NAMES_EN,
    LANG_NAMES_ZH,
    STYLE_INSTRUCTIONS,
    _split_by_sentences,
    _setup_cuda_dll_path,
)

logger = logging.getLogger(__name__)

# GGUF 模型變體（含多量化選項）
MODEL_VARIANTS = {
    "4b": {
        "Q4_K_M": {"repo_id": "mradermacher/translategemma-4b-it-GGUF", "filename": "translategemma-4b-it.Q4_K_M.gguf", "size_mb": 2500},
    },
    "12b": {
        "Q4_K_M": {"repo_id": "mradermacher/translategemma-12b-it-GGUF", "filename": "translategemma-12b-it.Q4_K_M.gguf", "size_mb": 7300},
        "Q4_K_S": {"repo_id": "mradermacher/translategemma-12b-it-GGUF", "filename": "translategemma-12b-it.Q4_K_S.gguf", "size_mb": 6940},
        "Q3_K_L": {"repo_id": "mradermacher/translategemma-12b-it-GGUF", "filename": "translategemma-12b-it.Q3_K_L.gguf", "size_mb": 6480},
        "Q3_K_M": {"repo_id": "mradermacher/translategemma-12b-it-GGUF", "filename": "translategemma-12b-it.Q3_K_M.gguf", "size_mb": 6010},
        "Q3_K_S": {"repo_id": "mradermacher/translategemma-12b-it-GGUF", "filename": "translategemma-12b-it.Q3_K_S.gguf", "size_mb": 5460},
    },
    "27b": {
        "Q4_K_M": {"repo_id": "bullerwins/translategemma-27b-it-GGUF", "filename": "translategemma-27b-it-Q4_K_M.gguf", "size_mb": 16500},
    },
}

DEFAULT_QUANT = {"4b": "Q4_K_M", "12b": "Q4_K_M", "27b": "Q4_K_M"}


class TranslateGemmaWrapper(BaseTranslator):
    """
    TranslateGemma 封裝類別（llama.cpp GGUF 版）
    使用 Gemma 2 chat template 格式
    """

    MODEL_VARIANTS = MODEL_VARIANTS
    DEFAULT_QUANT = DEFAULT_QUANT
    SLOT = SLOT_TRANSLATEGEMMA
    MODEL_NAME = "TranslateGemma"
    _MODELS_DIR = get_models_dir("translategemma")
    _MODEL_LAYERS = {"4b": 26, "12b": 40, "27b": 64}
    _VRAM_OVERHEAD_MB = {"4b": 400, "12b": 800, "27b": 1200}
    _MODEL_N_CTX = {"4b": 2048, "12b": 1024, "27b": 512}

    def _generate_translation(
        self, text: str, source_lang: str, target_lang: str,
        glossary: Optional[dict[str, str]] = None,
    ) -> str:
        """使用 Gemma 2 chat template 格式翻譯一般文字"""
        source_name = LANG_NAMES_EN.get(source_lang, source_lang)
        target_name = LANG_NAMES_EN.get(target_lang, target_lang)

        glossary_text = self._format_glossary(glossary)
        user_msg = (
            f"Translate the following {source_name} text to {target_name}. "
            f"Output only the translation, no explanations."
            f"{glossary_text}\n\n"
            f"{text}"
        )
        prompt = f"<start_of_turn>user\n{user_msg}<end_of_turn>\n<start_of_turn>model\n"

        output = self._model(
            prompt,
            max_tokens=max(len(text) * 4, 100),
            temperature=0.1,
            echo=False,
            stop=["<end_of_turn>"],
        )

        return output["choices"][0]["text"].strip()

    def _generate_srt_translation(
        self,
        srt_text: str,
        source_lang: str,
        target_lang: str,
        keep_names: bool = True,
        style: str = "colloquial",
        glossary: Optional[dict[str, str]] = None,
    ) -> str:
        """使用 Gemma 2 chat template 格式翻譯 SRT"""
        target_zh = LANG_NAMES_ZH.get(target_lang, target_lang)
        style_text = STYLE_INSTRUCTIONS.get(style, STYLE_INSTRUCTIONS["colloquial"])

        if keep_names:
            name_instruction = "- 【重要】人名保持原文不翻譯，例如：アノン、友理、MyGO 等名字要保留原文"
        else:
            name_instruction = "- 人名可以翻譯成對應語言"

        glossary_text = self._format_glossary(glossary)

        user_msg = f"""將以下字幕翻譯成{target_zh}。

翻譯規則：
- 保持 SRT 格式和時間標籤不變
- {style_text}
{name_instruction}
- 只輸出翻譯結果
{glossary_text}
字幕：
{srt_text}"""
        prompt = f"<start_of_turn>user\n{user_msg}<end_of_turn>\n<start_of_turn>model\n"

        output = self._model(
            prompt,
            max_tokens=len(srt_text) * 3,
            temperature=0.1,
            echo=False,
            stop=["<end_of_turn>"],
        )

        return output["choices"][0]["text"].strip()


# 單例
_translategemma: Optional[TranslateGemmaWrapper] = None


def get_translategemma() -> TranslateGemmaWrapper:
    """取得 TranslateGemmaWrapper 單例"""
    global _translategemma
    if _translategemma is None:
        _translategemma = TranslateGemmaWrapper()
    return _translategemma
