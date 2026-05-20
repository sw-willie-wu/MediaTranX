"""Language constants and translation style options.

Pure data module — no domain logic, no engine dependencies.
"""
from __future__ import annotations


# Whisper language codes (ISO 639-1) -> BCP 47
WHISPER_TO_BCP47 = {
    "zh": "zh-TW",
    "zh-TW": "zh-TW",
    "zh-CN": "zh-CN",
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
    {"value": "",      "label": ""},
    {"value": "zh-TW", "label": "繁體中文"},
    {"value": "zh-CN", "label": "简体中文"},
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

# Translation style instructions (English, used in prompts sent to the model)
STYLE_INSTRUCTIONS = {
    "colloquial": "Use a colloquial, conversational translation style",
    "formal": "Use a formal, written translation style",
    "literal": "Translate as literally as possible, preserving original structure",
}
