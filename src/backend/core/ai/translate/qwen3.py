"""
Qwen3 翻譯模組 (REFACTOR V3)
重構: 移除內部模型註冊，改由 registry.py 管理。
保持所有翻譯 Prompt 與邏輯細節不變。

TODO (未來重構):
- 將 SRT 解析/格式化邏輯移至 subtitle_utils.py
- 將 BaseTranslator 簡化為純翻譯器（繼承 GGUFRuntime）
- 批次處理邏輯移至 Service 層
參考: REFACTOR_COMPLETED.md 中的職責邊界分析
"""
import logging
from typing import Optional

from backend.core.ai.registry import SLOT_LLM, MODELS_REGISTRY
from .base import (
    BaseTranslator,
    LANG_NAMES_EN,
    LANG_NAMES_ZH,
    STYLE_INSTRUCTIONS,
)

logger = logging.getLogger(__name__)

class Qwen3Wrapper(BaseTranslator):
    """
    Qwen3 封裝類別（llama.cpp GGUF 版）
    
    TODO: 未來應重構為繼承 GGUFRuntime，移除內部的模型載入邏輯
    """
    SLOT = SLOT_LLM
    MODEL_NAME = "Qwen3"
    CATEGORY = "qwen3"

    # 完整繼承自 registry.py 的配置
    @property
    def MODEL_VARIANTS(self): return MODELS_REGISTRY[self.CATEGORY]["variants"]
    @property
    def DEFAULT_QUANT(self): return MODELS_REGISTRY[self.CATEGORY]["default_quant"]
    @property
    def _MODEL_LAYERS(self): return MODELS_REGISTRY[self.CATEGORY]["layers"]
    @property
    def _VRAM_OVERHEAD_MB(self): return MODELS_REGISTRY[self.CATEGORY]["vram_overhead_mb"]
    @property
    def _MODEL_N_CTX(self): return MODELS_REGISTRY[self.CATEGORY]["n_ctx"]

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
