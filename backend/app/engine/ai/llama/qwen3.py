"""
Qwen3 翻譯模組（LlamaServerRuntime 版）
透過 llama-server subprocess 執行推理，移除手動 ChatML 格式化。
"""
import logging
from typing import Optional

from app.engine.ai.registry import SLOT_LLM
from app.engine.ai.base.translate import (
    BaseTranslator,
    LANG_NAMES_EN,
    LANG_NAMES_ZH,
    STYLE_INSTRUCTIONS,
)

logger = logging.getLogger(__name__)


class Qwen3Wrapper(BaseTranslator):
    """Qwen3 封裝類別（llama-server 版）"""
    SLOT = SLOT_LLM
    MODEL_NAME = "Qwen3"
    MODEL_ID = "qwen3"

    def _generate_translation(
        self, text: str, source_lang: str, target_lang: str,
        glossary: Optional[dict[str, str]] = None,
    ) -> str:
        source_name = LANG_NAMES_EN.get(source_lang, source_lang)
        target_name = LANG_NAMES_EN.get(target_lang, target_lang)
        glossary_text = self._format_glossary(glossary)

        user_msg = (
            f"Translate the following {source_name} text to {target_name}. "
            f"Output only the translation, no explanations."
            f"{glossary_text}\n\n"
            f"{text} /no_think"
        )

        return self._runtime.chat(
            messages=[
                {"role": "system", "content": "You are a professional subtitle translator."},
                {"role": "user", "content": user_msg},
            ],
            max_tokens=max(len(text) * 4, 100),
            temperature=0.1,
        )

    def _generate_srt_translation(
        self,
        srt_text: str,
        source_lang: str,
        target_lang: str,
        keep_names: bool = True,
        style: str = "colloquial",
        glossary: Optional[dict[str, str]] = None,
    ) -> str:
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
{srt_text} /no_think"""

        return self._runtime.chat(
            messages=[
                {"role": "system", "content": "You are a professional subtitle translator."},
                {"role": "user", "content": user_msg},
            ],
            max_tokens=len(srt_text) * 3,
            temperature=0.1,
        )


# 單例
_qwen3: Optional[Qwen3Wrapper] = None


def get_qwen3() -> Qwen3Wrapper:
    """取得 Qwen3Wrapper 單例"""
    global _qwen3
    if _qwen3 is None:
        _qwen3 = Qwen3Wrapper()
    return _qwen3
