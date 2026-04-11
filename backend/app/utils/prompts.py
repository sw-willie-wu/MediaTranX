"""
Prompt templates, constants, and utility functions for translation and VLM OCR.

This is a pure utility module -- importing app.engine.* is prohibited.
All LlamaServerRuntime calls are handled by the service layer.
"""
import base64
import io
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from PIL import Image

logger = logging.getLogger(__name__)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Language constants
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# Whisper language codes (ISO 639-1) -> BCP 47
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

# Supported target languages (for API response; name uses each language's own name)
SUPPORTED_LANGUAGES = [
    {"code": "zh-TW", "name": "繁體中文"},
    {"code": "zh-CN", "name": "简体中文"},
    {"code": "en", "name": "English"},
    {"code": "ja", "name": "日本語"},
    {"code": "ko", "name": "한국어"},
    {"code": "fr", "name": "Français"},
    {"code": "de", "name": "Deutsch"},
    {"code": "es", "name": "Español"},
    {"code": "ru", "name": "Русский"},
    {"code": "pt", "name": "Português"},
    {"code": "it", "name": "Italiano"},
    {"code": "th", "name": "ไทย"},
    {"code": "vi", "name": "Tiếng Việt"},
    {"code": "ar", "name": "العربية"},
    {"code": "hi", "name": "हिन्दी"},
    {"code": "id", "name": "Bahasa Indonesia"},
    {"code": "nl", "name": "Nederlands"},
    {"code": "pl", "name": "Polski"},
    {"code": "sv", "name": "Svenska"},
    {"code": "tr", "name": "Türkçe"},
    {"code": "uk", "name": "Українська"},
]

# Language name lookup (English)
LANG_NAMES_EN = {
    "en": "English", "zh-TW": "Traditional Chinese", "zh-CN": "Simplified Chinese",
    "ja": "Japanese", "ko": "Korean", "fr": "French", "de": "German",
    "es": "Spanish", "ru": "Russian", "pt": "Portuguese", "it": "Italian",
    "th": "Thai", "vi": "Vietnamese", "ar": "Arabic", "hi": "Hindi",
    "id": "Indonesian", "nl": "Dutch", "pl": "Polish", "sv": "Swedish",
    "tr": "Turkish", "uk": "Ukrainian",
}

# Language name lookup (Chinese)
LANG_NAMES_ZH = {
    "zh-TW": "繁體中文", "zh-CN": "簡體中文", "en": "英文",
    "ja": "日文", "ko": "韓文", "fr": "法文", "de": "德文",
    "es": "西班牙文", "ru": "俄文", "pt": "葡萄牙文", "it": "義大利文",
    "th": "泰文", "vi": "越南文", "ar": "阿拉伯文", "hi": "印地文",
    "id": "印尼文", "nl": "荷蘭文", "pl": "波蘭文", "sv": "瑞典文",
    "tr": "土耳其文", "uk": "烏克蘭文",
}

# Whisper language options (for API response; label uses each language's own name)
WHISPER_LANGUAGE_OPTIONS = [
    {"value": "",   "label": ""},
    {"value": "zh", "label": "中文"},
    {"value": "en", "label": "English"},
    {"value": "ja", "label": "日本語"},
    {"value": "ko", "label": "한국어"},
    {"value": "fr", "label": "Français"},
    {"value": "de", "label": "Deutsch"},
    {"value": "es", "label": "Español"},
    {"value": "ru", "label": "Русский"},
    {"value": "pt", "label": "Português"},
    {"value": "it", "label": "Italiano"},
    {"value": "th", "label": "ไทย"},
    {"value": "vi", "label": "Tiếng Việt"},
    {"value": "ar", "label": "العربية"},
    {"value": "hi", "label": "हिन्दी"},
    {"value": "id", "label": "Bahasa Indonesia"},
    {"value": "nl", "label": "Nederlands"},
    {"value": "pl", "label": "Polski"},
    {"value": "sv", "label": "Svenska"},
    {"value": "tr", "label": "Türkçe"},
    {"value": "uk", "label": "Українська"},
]

# Translation style options (for API response)
STYLE_OPTIONS = [
    {"value": "colloquial", "label": "口語化"},
    {"value": "formal",     "label": "正式"},
    {"value": "literal",    "label": "直譯"},
]

# Translation style instructions (Chinese, used in prompts sent to the model)
STYLE_INSTRUCTIONS = {
    "colloquial": "使用口語化的翻譯風格",
    "formal": "使用正式、書面的翻譯風格",
    "literal": "盡量直譯，保持原文結構",
}

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Inference parameter defaults
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

TRANSLATE_PARAMS = {"temperature": 0.1, "top_k": 40, "top_p": 0.9}
SUMMARIZE_PARAMS = {"temperature": 0.3, "top_k": 40, "top_p": 0.9}
OCR_PARAMS = {"temperature": 0.1, "top_k": 40, "top_p": 0.9}

# Model-specific config: system prompt and text suffix per model
MODEL_CONFIGS = {
    "qwen3": {
        "system_prompt": "You are a professional subtitle translator.",
        "text_suffix": " /no_think",
    },
    "qwen3.5": {
        "system_prompt": "You are a professional subtitle translator.",
        "text_suffix": "",
    },
    "translategemma": {
        "system_prompt": None,
        "text_suffix": "",
    },
}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Translation result dataclass
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@dataclass
class TranslateResult:
    """Translation result."""
    source_language: str
    target_language: str
    text: str
    model_size: str


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  SRT utility functions
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def format_glossary(glossary: Optional[dict[str, str]]) -> str:
    """Format a glossary dict into a prompt paragraph."""
    if not glossary:
        return ""
    lines = "\n".join(f"- {src} → {tgt}" for src, tgt in glossary.items())
    return (
        f"\n專有名詞對照表（翻譯時請嚴格依照此表，"
        f"名稱在字幕中可能以片假名、平假名、簡稱等不同形式出現，請自行對應）：\n{lines}\n"
    )


def format_srt_time(seconds: float) -> str:
    """Format seconds into SRT time format (HH:MM:SS,mmm)."""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds % 1) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def segments_to_srt(segments: list[dict], start_index: int = 1) -> str:
    """Convert segments to SRT format string."""
    lines = []
    for i, seg in enumerate(segments, start_index):
        start_time = format_srt_time(seg["start"])
        end_time = format_srt_time(seg["end"])
        lines.append(f"{i}")
        lines.append(f"{start_time} --> {end_time}")
        lines.append(seg["text"])
        lines.append("")
    return "\n".join(lines)


def parse_srt_response(srt_text: str, original_segments: list[dict]) -> list[dict]:
    """Parse translated SRT text and return segments."""
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


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Text splitting functions
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def split_by_sentences(text: str, max_chars: int) -> list[str]:
    """Split text on sentence boundaries."""
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


def split_text(text: str, max_chars: int = 1500) -> list[str]:
    """Split long text into translation-friendly chunks."""
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
                chunks.extend(split_by_sentences(para, max_chars))
                current_chunk = ""
            else:
                current_chunk = para

    if current_chunk:
        chunks.append(current_chunk)

    return chunks


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Translation prompt builders
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def build_translate_prompt(
    text: str,
    source_lang: str,
    target_lang: str,
    glossary: Optional[dict[str, str]] = None,
    model_id: str = "translategemma",
) -> str:
    """Build a translation prompt for chat"""
    source_name = LANG_NAMES_EN.get(source_lang, source_lang)
    target_name = LANG_NAMES_EN.get(target_lang, target_lang)
    glossary_text = format_glossary(glossary)
    config = MODEL_CONFIGS.get(model_id, MODEL_CONFIGS["translategemma"])
    suffix = config["text_suffix"]

    return (
        f"Translate the following {source_name} text to {target_name}. "
        f"Output only the translation, no explanations."
        f"{glossary_text}\n\n"
        f"{text}{suffix}"
    )


def build_srt_translate_prompt(
    srt_text: str,
    source_lang: str,
    target_lang: str,
    keep_names: bool = True,
    style: str = "colloquial",
    glossary: Optional[dict[str, str]] = None,
    model_id: str = "translategemma",
) -> str:
    """Build SRT translation prompt"""
    target_zh = LANG_NAMES_ZH.get(target_lang, target_lang)
    style_text = STYLE_INSTRUCTIONS.get(style, STYLE_INSTRUCTIONS["colloquial"])
    config = MODEL_CONFIGS.get(model_id, MODEL_CONFIGS["translategemma"])
    suffix = config["text_suffix"]

    if keep_names:
        name_instruction = "- 【重要】人名保持原文不翻譯，例如：アノン、友理、MyGO 等名字要保留原文"
    else:
        name_instruction = "- 人名可以翻譯成對應語言"

    glossary_text = format_glossary(glossary)

    return f"""將以下字幕翻譯成{target_zh}。

翻譯規則：
- 保持 SRT 格式和時間標籤不變
- {style_text}
{name_instruction}
- 只輸出翻譯結果
{glossary_text}
字幕：
{srt_text}{suffix}"""


def build_translate_messages(
    prompt: str,
    model_id: str = "translategemma",
) -> list[dict]:
    """Build a messages list based on model configuration."""
    config = MODEL_CONFIGS.get(model_id, MODEL_CONFIGS["translategemma"])
    messages = []
    if config["system_prompt"]:
        messages.append({"role": "system", "content": config["system_prompt"]})
    messages.append({"role": "user", "content": prompt})
    return messages


def build_summarize_prompt(text: str) -> str:
    """Build a prompt for generating a bullet-point outline summary of a transcript."""
    return (
        "Generate a bullet-point outline summary of the following transcript. "
        "Write the summary in the same language as the transcript text:\n\n"
        f"{text}"
    )


def build_chunk_summarize_prompt(text: str) -> str:
    """Build a prompt for summarizing a single chunk of a long transcript."""
    return (
        "Summarize the following transcript segment into key bullet points. "
        "Keep it concise. Write in the same language as the text:\n\n"
        f"{text}"
    )


def build_merge_summaries_prompt(summaries: str) -> str:
    """Build a prompt for merging multiple chunk summaries into a final outline."""
    return (
        "The following are summaries of consecutive parts of a transcript. "
        "Merge them into a single coherent bullet-point outline. "
        "Remove duplicates and organize by topic. "
        "Write in the same language as the summaries:\n\n"
        f"{summaries}"
    )


# ── Token estimation ─────────────────────────────────────────────────────
# Rough estimate: 1 token ≈ 3.5 characters for mixed CJK/English text
_CHARS_PER_TOKEN = 3.5


def split_text_for_context(text: str, max_tokens: int = 3000) -> list[str]:
    """
    Split text into chunks that fit within a token budget.
    Splits on paragraph boundaries (double newline), falls back to sentences.
    """
    max_chars = int(max_tokens * _CHARS_PER_TOKEN)

    if len(text) <= max_chars:
        return [text]

    chunks: list[str] = []
    paragraphs = text.split("\n")

    current_chunk: list[str] = []
    current_len = 0

    for para in paragraphs:
        para_len = len(para) + 1  # +1 for newline
        if current_len + para_len > max_chars and current_chunk:
            chunks.append("\n".join(current_chunk))
            current_chunk = []
            current_len = 0
        current_chunk.append(para)
        current_len += para_len

    if current_chunk:
        chunks.append("\n".join(current_chunk))

    return chunks


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  VLM OCR constants and prompt builders
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

DEFAULT_VLM_MODEL = "qwen3vl"

# OCR prompt -- ignore visual elements
_IGNORE_VISUAL = (
    "Ignore QR codes, barcodes, logos, icons, and any purely visual/graphical elements — "
    "extract only human-readable text."
)

# OCR prompt -- plain text mode
OCR_SYSTEM_TXT = (
    "You are an OCR assistant. Extract all text from the image exactly as it appears. "
    "Output only the extracted text, preserving line breaks and layout as much as possible. "
    f"{_IGNORE_VISUAL} "
    "Do not add explanations, commentary, or any formatting markers."
)

OCR_USER_TXT = (
    "Please extract all human-readable text from this image. "
    "Output only the plain text content, nothing else."
)

# OCR prompt -- Markdown mode
OCR_SYSTEM_MD = (
    "You are an OCR assistant. Extract all text from the image and format the output in Markdown. "
    f"{_IGNORE_VISUAL} "
    "Rules:\n"
    "- If the image contains a table, represent it as a Markdown table (| col | col | with --- separator row).\n"
    "- Use # headings for titles or section headers you can identify.\n"
    "- Preserve paragraph breaks with blank lines.\n"
    "- Output only the extracted content in Markdown format, no explanations or commentary."
)

OCR_USER_MD = (
    "Please extract all human-readable text from this image and format it in Markdown. "
    "Represent any tables as Markdown tables. Output only the Markdown content."
)


def build_ocr_messages(image_path: str, format: str = "md") -> list[dict]:
    """
    Build VLM OCR messages array (including base64 image).

    Args:
        image_path: Path to the image file
        format: "md" (Markdown) or "txt" (plain text)

    Returns:
        Messages list ready to pass to runtime.chat()
    """
    # Read image; llama-server (stb_image) does not support webp, convert to PNG
    image_bytes = Path(image_path).read_bytes()
    ext = Path(image_path).suffix.lower().lstrip(".")

    if ext == "webp":
        img = Image.open(io.BytesIO(image_bytes))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        image_bytes = buf.getvalue()
        mime = "image/png"
    else:
        mime = {
            "jpg": "image/jpeg", "jpeg": "image/jpeg",
            "png": "image/png", "gif": "image/gif",
            "bmp": "image/bmp",
        }.get(ext, "image/jpeg")

    b64 = base64.b64encode(image_bytes).decode("ascii")
    data_url = f"data:{mime};base64,{b64}"

    sys_prompt = OCR_SYSTEM_MD if format == "md" else OCR_SYSTEM_TXT
    user_prompt = OCR_USER_MD if format == "md" else OCR_USER_TXT

    return [
        {"role": "system", "content": sys_prompt},
        {
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": data_url}},
                {"type": "text", "text": user_prompt},
            ],
        },
    ]
