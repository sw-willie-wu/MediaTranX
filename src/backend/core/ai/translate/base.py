"""
翻譯模型基礎類別
將 TranslateGemma 和 Qwen3 的共用邏輯抽出，子類只需覆寫 prompt 建構方法
"""
import logging
import re
import threading
from abc import abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from backend.core.ai.model_manager import get_model_manager

logger = logging.getLogger(__name__)

# === 共用常數 ===

# Whisper 語言代碼 (ISO 639-1) → BCP 47
WHISPER_TO_BCP47 = {
    "zh": "zh-CN",
    "en": "en",
    "ja": "ja",
    "ko": "ko",
    "fr": "fr",
    "de": "de",
    "es": "es",
    "ru": "ru",
    "pt": "pt",
    "it": "it",
    "th": "th",
    "vi": "vi",
    "ar": "ar",
    "hi": "hi",
    "id": "id",
    "nl": "nl",
    "pl": "pl",
    "sv": "sv",
    "tr": "tr",
    "uk": "uk",
}

# 支援的目標語言列表（供 API 回傳）
SUPPORTED_LANGUAGES = [
    {"code": "zh-TW", "name": "繁體中文"},
    {"code": "zh-CN", "name": "簡體中文"},
    {"code": "en", "name": "英文"},
    {"code": "ja", "name": "日文"},
    {"code": "ko", "name": "韓文"},
    {"code": "fr", "name": "法文"},
    {"code": "de", "name": "德文"},
    {"code": "es", "name": "西班牙文"},
    {"code": "ru", "name": "俄文"},
    {"code": "pt", "name": "葡萄牙文"},
    {"code": "it", "name": "義大利文"},
    {"code": "th", "name": "泰文"},
    {"code": "vi", "name": "越南文"},
    {"code": "ar", "name": "阿拉伯文"},
    {"code": "hi", "name": "印地文"},
    {"code": "id", "name": "印尼文"},
    {"code": "nl", "name": "荷蘭文"},
    {"code": "pl", "name": "波蘭文"},
    {"code": "sv", "name": "瑞典文"},
    {"code": "tr", "name": "土耳其文"},
    {"code": "uk", "name": "烏克蘭文"},
]

# 語言名稱對照（英文）
LANG_NAMES_EN = {
    "en": "English", "zh-TW": "Traditional Chinese", "zh-CN": "Simplified Chinese",
    "ja": "Japanese", "ko": "Korean", "fr": "French", "de": "German",
    "es": "Spanish", "ru": "Russian", "pt": "Portuguese", "it": "Italian",
    "th": "Thai", "vi": "Vietnamese", "ar": "Arabic", "hi": "Hindi",
    "id": "Indonesian", "nl": "Dutch", "pl": "Polish", "sv": "Swedish",
    "tr": "Turkish", "uk": "Ukrainian",
}

# 語言名稱對照（中文）
LANG_NAMES_ZH = {
    "zh-TW": "繁體中文", "zh-CN": "簡體中文", "en": "英文",
    "ja": "日文", "ko": "韓文", "fr": "法文", "de": "德文",
    "es": "西班牙文", "ru": "俄文", "pt": "葡萄牙文", "it": "義大利文",
    "th": "泰文", "vi": "越南文", "ar": "阿拉伯文", "hi": "印地文",
    "id": "印尼文", "nl": "荷蘭文", "pl": "波蘭文", "sv": "瑞典文",
    "tr": "土耳其文", "uk": "烏克蘭文",
}

# Whisper 語言選項（供 API 回傳）
WHISPER_LANGUAGE_OPTIONS = [
    {"value": "",   "label": "自動偵測"},
    {"value": "zh", "label": "中文"},
    {"value": "en", "label": "英文"},
    {"value": "ja", "label": "日文"},
    {"value": "ko", "label": "韓文"},
    {"value": "fr", "label": "法文"},
    {"value": "de", "label": "德文"},
    {"value": "es", "label": "西班牙文"},
    {"value": "ru", "label": "俄文"},
    {"value": "pt", "label": "葡萄牙文"},
    {"value": "it", "label": "義大利文"},
    {"value": "th", "label": "泰文"},
    {"value": "vi", "label": "越南文"},
    {"value": "ar", "label": "阿拉伯文"},
    {"value": "hi", "label": "印地文"},
    {"value": "id", "label": "印尼文"},
    {"value": "nl", "label": "荷蘭文"},
    {"value": "pl", "label": "波蘭文"},
    {"value": "sv", "label": "瑞典文"},
    {"value": "tr", "label": "土耳其文"},
    {"value": "uk", "label": "烏克蘭文"},
]

# 翻譯風格選項（供 API 回傳）
STYLE_OPTIONS = [
    {"value": "colloquial", "label": "口語化"},
    {"value": "formal",     "label": "正式"},
    {"value": "literal",    "label": "直譯"},
]

# 翻譯風格說明
STYLE_INSTRUCTIONS = {
    "colloquial": "使用口語化的翻譯風格",
    "formal": "使用正式、書面的翻譯風格",
    "literal": "盡量直譯，保持原文結構",
}


@dataclass
class TranslateResult:
    """翻譯結果"""
    source_language: str
    target_language: str
    text: str
    model_size: str


def _split_by_sentences(text: str, max_chars: int) -> list[str]:
    """按句子邊界拆分文字"""
    sentences = re.split(r'(?<=[。！？.!?\n])\s*', text)
    chunks = []
    current = ""

    for sent in sentences:
        if not sent:
            continue
        if not current:
            current = sent
        elif len(current) + len(sent) + 1 <= max_chars:
            current += " " + sent
        else:
            chunks.append(current)
            current = sent

    if current:
        chunks.append(current)

    return chunks


class BaseTranslator:
    """
    翻譯模型共用基礎類別（LlamaServerRuntime 版）

    子類必須覆寫：
    - CLASS ATTRS: SLOT, MODEL_NAME, MODEL_ID
    - METHODS: _generate_translation(), _generate_srt_translation()
    """

    # === 子類必須覆寫的 class attrs ===
    SLOT: str = ""          # ModelManager slot 名稱
    MODEL_NAME: str = ""    # 顯示名稱（用於 log）
    MODEL_ID: str = ""      # registry 中的 model_id（如 "qwen3", "translategemma"）

    def __init__(self):
        from backend.core.ai.base.llama_server_runtime import LlamaServerRuntime
        self._runtime = LlamaServerRuntime(self.SLOT)
        self._lock = threading.RLock()
        # LlamaServerRuntime.__init__ 已透過 BaseRuntime 自動向 ModelManager 註冊 unloader

    def get_model_status(self, model_size: str = "4b", quantization: Optional[str] = None) -> dict:
        """查詢模型狀態（llama-server 二進位 + 模型檔案）"""
        available = get_model_manager().is_llama_ready()

        variant = f"{model_size}:{quantization}" if quantization else model_size
        model_downloaded = (
            get_model_manager().get_model_path(self.MODEL_ID, variant) is not None
        )

        return {
            "available": available,
            "model_size": model_size,
            "model_downloaded": model_downloaded,
        }

    @staticmethod
    def _format_glossary(glossary: Optional[dict[str, str]]) -> str:
        """將 glossary dict 格式化為 prompt 段落"""
        if not glossary:
            return ""
        lines = "\n".join(f"- {src} → {tgt}" for src, tgt in glossary.items())
        return (
            f"\n專有名詞對照表（翻譯時請嚴格依照此表，"
            f"名稱在字幕中可能以片假名、平假名、簡稱等不同形式出現，請自行對應）：\n{lines}\n"
        )

    def _format_srt_time(self, seconds: float) -> str:
        """將秒數格式化為 SRT 時間格式 (HH:MM:SS,mmm)"""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        millis = int((seconds % 1) * 1000)
        return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"

    def _segments_to_srt(self, segments: list[dict], start_index: int = 1) -> str:
        """將 segments 轉換為 SRT 格式字串"""
        lines = []
        for i, seg in enumerate(segments, start_index):
            start_time = self._format_srt_time(seg["start"])
            end_time = self._format_srt_time(seg["end"])
            lines.append(f"{i}")
            lines.append(f"{start_time} --> {end_time}")
            lines.append(seg["text"])
            lines.append("")
        return "\n".join(lines)

    def _parse_srt_response(self, srt_text: str, original_segments: list[dict]) -> list[dict]:
        """解析翻譯後的 SRT 格式，回傳 segments"""
        pattern = r'(\d+)\s*\n(\d{2}:\d{2}:\d{2},\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2},\d{3})\s*\n([\s\S]*?)(?=\n\n\d+\s*\n|\n*$)'
        matches = re.findall(pattern, srt_text.strip() + "\n\n")

        translated = []
        for i, orig_seg in enumerate(original_segments):
            if i < len(matches):
                _, _, _, text = matches[i]
                cleaned = text.strip()
                translated.append({
                    "start": orig_seg["start"],
                    "end": orig_seg["end"],
                    "text": cleaned if cleaned else orig_seg["text"],
                })
            else:
                translated.append(orig_seg)

        return translated

    # === 子類必須覆寫的方法 ===

    @abstractmethod
    def _generate_translation(
        self, text: str, source_lang: str, target_lang: str,
        glossary: Optional[dict[str, str]] = None,
    ) -> str:
        """翻譯一般文字（子類覆寫以套用不同 prompt 格式）"""
        ...

    @abstractmethod
    def _generate_srt_translation(
        self,
        srt_text: str,
        source_lang: str,
        target_lang: str,
        keep_names: bool = True,
        style: str = "colloquial",
        glossary: Optional[dict[str, str]] = None,
    ) -> str:
        """翻譯 SRT 字幕（子類覆寫以套用不同 prompt 格式）"""
        ...

    # === 共用翻譯流程 ===

    def translate_segments(
        self,
        segments: list[dict],
        source_lang: str,
        target_lang: str,
        model_size: str = "4b",
        quantization: Optional[str] = None,
        on_progress: Optional[Callable[[float, str], None]] = None,
        batch_size: int = 5,
        keep_names: bool = True,
        style: str = "colloquial",
        glossary: Optional[dict[str, str]] = None,
    ) -> list[dict]:
        """批次翻譯字幕 segments（使用 SRT 格式）"""
        src = WHISPER_TO_BCP47.get(source_lang, source_lang)
        variant = f"{model_size}:{quantization}" if quantization else model_size

        with self._lock:
            def _load_progress(p, msg):
                if on_progress:
                    on_progress(p * 0.05, msg)

            if on_progress:
                on_progress(0.0, f"載入 {self.MODEL_NAME} 翻譯模型...")

            with self._runtime.acquire(self.MODEL_ID, variant, _load_progress):
                if on_progress:
                    on_progress(0.05, "開始翻譯字幕...")

                total = len(segments)
                translated = []
                num_batches = (total + batch_size - 1) // batch_size

                for batch_idx in range(num_batches):
                    start_idx = batch_idx * batch_size
                    end_idx = min(start_idx + batch_size, total)
                    batch_segments = segments[start_idx:end_idx]

                    srt_text = self._segments_to_srt(batch_segments, start_index=start_idx + 1)

                    translated_srt = self._generate_srt_translation(
                        srt_text, src, target_lang,
                        keep_names=keep_names,
                        style=style,
                        glossary=glossary,
                    )

                    batch_translated = self._parse_srt_response(translated_srt, batch_segments)
                    translated.extend(batch_translated)

                    if on_progress and num_batches > 0:
                        progress = min((batch_idx + 1) / num_batches, 1.0)
                        on_progress(
                            0.05 + progress * 0.95,
                            f"翻譯中... {end_idx}/{total} 段"
                        )

                if on_progress:
                    on_progress(1.0, "字幕翻譯完成")

                return translated

    def translate(
        self,
        text: str,
        source_lang: str,
        target_lang: str,
        model_size: str = "4b",
        quantization: Optional[str] = None,
        on_progress: Optional[Callable[[float, str], None]] = None,
        glossary: Optional[dict[str, str]] = None,
    ) -> TranslateResult:
        """長文翻譯，自動切 chunk"""
        variant = f"{model_size}:{quantization}" if quantization else model_size

        with self._lock:
            def _load_progress(p, msg):
                if on_progress:
                    on_progress(p * 0.05, msg)

            if on_progress:
                on_progress(0.0, f"載入 {self.MODEL_NAME} 翻譯模型...")

            with self._runtime.acquire(self.MODEL_ID, variant, _load_progress):
                if on_progress:
                    on_progress(0.05, "開始翻譯...")

                chunks = self._split_text(text, max_chars=1500)
                total = len(chunks)
                translated_chunks = []

                for i, chunk in enumerate(chunks):
                    result_text = self._generate_translation(chunk, source_lang, target_lang, glossary=glossary)
                    translated_chunks.append(result_text)

                    if on_progress and total > 0:
                        progress = min((i + 1) / total, 1.0)
                        on_progress(
                            0.05 + progress * 0.95,
                            f"翻譯中... {progress:.0%} ({i + 1}/{total} 段)"
                        )

                full_text = "\n\n".join(translated_chunks)

                if on_progress:
                    on_progress(1.0, "翻譯完成")

                return TranslateResult(
                    source_language=source_lang,
                    target_language=target_lang,
                    text=full_text,
                    model_size=model_size,
                )

    @staticmethod
    def _split_text(text: str, max_chars: int = 1500) -> list[str]:
        """將長文切割成適合翻譯的 chunks"""
        if len(text) <= max_chars:
            return [text]

        chunks = []
        paragraphs = text.split("\n\n")
        current_chunk = ""

        for para in paragraphs:
            if not current_chunk:
                current_chunk = para
            elif len(current_chunk) + len(para) + 2 <= max_chars:
                current_chunk += "\n\n" + para
            else:
                if current_chunk:
                    chunks.append(current_chunk)
                if len(para) > max_chars:
                    chunks.extend(_split_by_sentences(para, max_chars))
                    current_chunk = ""
                else:
                    current_chunk = para

        if current_chunk:
            chunks.append(current_chunk)

        return chunks
