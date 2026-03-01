"""
Qwen3 翻譯模組
使用 llama-cpp-python 載入 GGUF 量化模型，提供文字翻譯功能
模型不打包在 app 中，首次使用時自動從 HuggingFace 下載
"""
import logging
from pathlib import Path
from typing import Optional

from backend.core.paths import get_models_dir
from backend.core.ai.model_manager import SLOT_QWEN3
from .base import (
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
    "1.7b": {
        "Q8_0": {"repo_id": "Qwen/Qwen3-1.7B-GGUF", "filename": "Qwen3-1.7B-Q8_0.gguf", "size_mb": 1830},
    },
    "4b": {
        "Q4_K_M": {"repo_id": "Qwen/Qwen3-4B-GGUF", "filename": "Qwen3-4B-Q4_K_M.gguf", "size_mb": 2500},
    },
    "8b": {
        "Q4_K_M": {"repo_id": "Qwen/Qwen3-8B-GGUF", "filename": "Qwen3-8B-Q4_K_M.gguf", "size_mb": 5030},
    },
    "14b": {
        "Q4_K_M": {"repo_id": "Qwen/Qwen3-14B-GGUF", "filename": "Qwen3-14B-Q4_K_M.gguf", "size_mb": 9000},
        "Q4_K_S": {"repo_id": "unsloth/Qwen3-14B-GGUF", "filename": "Qwen3-14B-Q4_K_S.gguf", "size_mb": 8570},
        "Q3_K_M": {"repo_id": "unsloth/Qwen3-14B-GGUF", "filename": "Qwen3-14B-Q3_K_M.gguf", "size_mb": 7320},
        "Q3_K_S": {"repo_id": "unsloth/Qwen3-14B-GGUF", "filename": "Qwen3-14B-Q3_K_S.gguf", "size_mb": 6660},
    },
}

DEFAULT_QUANT = {"1.7b": "Q8_0", "4b": "Q4_K_M", "8b": "Q4_K_M", "14b": "Q4_K_M"}


class Qwen3Wrapper(BaseTranslator):
    """
    Qwen3 封裝類別（llama.cpp GGUF 版）
    使用 ChatML 格式 + /no_think
    """

    MODEL_VARIANTS = MODEL_VARIANTS
    DEFAULT_QUANT = DEFAULT_QUANT
    SLOT = SLOT_QWEN3
    MODEL_NAME = "Qwen3"
    _MODELS_DIR = get_models_dir("qwen3")
    _MODEL_LAYERS = {"1.7b": 28, "4b": 36, "8b": 36, "14b": 40}
    _VRAM_OVERHEAD_MB = {"1.7b": 300, "4b": 400, "8b": 800, "14b": 1000}
    _MODEL_N_CTX = {"1.7b": 2048, "4b": 2048, "8b": 1024, "14b": 512}

    def _generate_translation(
        self, text: str, source_lang: str, target_lang: str,
        glossary: Optional[dict[str, str]] = None,
    ) -> str:
        """使用 ChatML 格式翻譯一般文字"""
        source_name = LANG_NAMES_EN.get(source_lang, source_lang)
        target_name = LANG_NAMES_EN.get(target_lang, target_lang)

        glossary_text = self._format_glossary(glossary)
        user_msg = (
            f"Translate the following {source_name} text to {target_name}. "
            f"Output only the translation, no explanations."
            f"{glossary_text}\n\n"
            f"{text}"
        )
        prompt = (
            f"<|im_start|>system\nYou are a professional subtitle translator.<|im_end|>\n"
            f"<|im_start|>user\n{user_msg} /no_think<|im_end|>\n"
            f"<|im_start|>assistant\n"
        )

        output = self._model(
            prompt,
            max_tokens=max(len(text) * 4, 100),
            temperature=0.1,
            echo=False,
            stop=["<|im_end|>"],
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
        """使用 ChatML 格式翻譯 SRT"""
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
        prompt = (
            f"<|im_start|>system\nYou are a professional subtitle translator.<|im_end|>\n"
            f"<|im_start|>user\n{user_msg} /no_think<|im_end|>\n"
            f"<|im_start|>assistant\n"
        )

        output = self._model(
            prompt,
            max_tokens=len(srt_text) * 3,
            temperature=0.1,
            echo=False,
            stop=["<|im_end|>"],
        )

        return output["choices"][0]["text"].strip()


# 單例
_qwen3: Optional[Qwen3Wrapper] = None


def get_qwen3() -> Qwen3Wrapper:
    """取得 Qwen3Wrapper 單例"""
    global _qwen3
    if _qwen3 is None:
        _qwen3 = Qwen3Wrapper()
    return _qwen3
