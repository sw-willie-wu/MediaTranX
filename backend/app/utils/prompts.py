"""Prompt templates and per-model prompt builders.

This is a pure utility module -- importing app.adapters.* is prohibited.
Language constants live in utils/languages.py; SRT helpers in utils/subtitles.py;
text chunking in utils/text_chunking.py; VLM chat message assembly (with PIL)
in utils/vision_messages.py.
"""
from __future__ import annotations
import logging
from typing import Optional

from app.utils.languages import (
    LANG_NAMES_EN,
    LANG_NAMES_ZH,
    STYLE_INSTRUCTIONS,
)
from app.utils.vision_messages import build_ocr_messages

logger = logging.getLogger(__name__)

# Default VLM family (used when no explicit family is requested)
DEFAULT_VLM_MODEL = "qwen3vl"

# Per-family chat envelope for legacy build_translate_prompt / build_srt_translate_prompt.
# (Prompt template config: system role + text suffix; not inference params.)
MODEL_CONFIGS = {
    "gemma4": {"system_prompt": "You are a professional subtitle translator.", "text_suffix": ""},
    "qwen3": {"system_prompt": "You are a professional subtitle translator.", "text_suffix": " /no_think"},
    "qwen3.5": {"system_prompt": "You are a professional subtitle translator.", "text_suffix": ""},
}


def format_glossary(glossary: Optional[dict[str, str]]) -> str:
    """Format a glossary dict into a prompt paragraph."""
    if not glossary:
        return ""
    lines = "\n".join(f"- {src} → {tgt}" for src, tgt in glossary.items())
    return (
        f"\n專有名詞對照表（翻譯時請嚴格依照此表，"
        f"名稱在字幕中可能以片假名、平假名、簡稱等不同形式出現，請自行對應）：\n{lines}\n"
    )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Legacy text/SRT translation prompt builders
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def build_translate_prompt(
    text: str,
    source_lang: str,
    target_lang: str,
    glossary: Optional[dict[str, str]] = None,
    model_id: str = "gemma4",
) -> str:
    """Build a translation prompt for chat."""
    source_name = LANG_NAMES_EN.get(source_lang, source_lang)
    target_name = LANG_NAMES_EN.get(target_lang, target_lang)
    glossary_text = format_glossary(glossary)
    config = MODEL_CONFIGS.get(model_id, MODEL_CONFIGS["gemma4"])
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
    model_id: str = "gemma4",
) -> str:
    """Build SRT translation prompt."""
    target_zh = LANG_NAMES_ZH.get(target_lang, target_lang)
    style_text = STYLE_INSTRUCTIONS.get(style, STYLE_INSTRUCTIONS["colloquial"])
    config = MODEL_CONFIGS.get(model_id, MODEL_CONFIGS["gemma4"])
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


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Summarize prompt builders
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _summarize_lang_instruction(source_lang: Optional[str] = None) -> str:
    """Build the language instruction fragment for summarize prompts."""
    if source_lang:
        lang_name = LANG_NAMES_EN.get(source_lang, source_lang)
        return f"Write the summary in {lang_name}."
    return "Write the summary in the same language as the text."


def build_summarize_prompt(text: str, source_lang: Optional[str] = None) -> str:
    """Build a prompt for generating a Markdown outline summary of a transcript."""
    lang_inst = _summarize_lang_instruction(source_lang)
    return (
        "Generate an outline summary of the following transcript in Markdown format. "
        "Use ## for section headings and - for bullet points. "
        f"{lang_inst}\n\n"
        f"{text}"
    )


def build_chunk_summarize_prompt(text: str, source_lang: Optional[str] = None) -> str:
    """Build a prompt for summarizing a single chunk of a long transcript."""
    lang_inst = _summarize_lang_instruction(source_lang)
    return (
        "Summarize the following transcript segment in Markdown format. "
        "Use - for bullet points. Keep it concise. "
        f"{lang_inst}\n\n"
        f"{text}"
    )


def build_merge_summaries_prompt(summaries: str, source_lang: Optional[str] = None) -> str:
    """Build a prompt for merging multiple chunk summaries into a final outline."""
    lang_inst = _summarize_lang_instruction(source_lang)
    return (
        "The following are summaries of consecutive parts of a transcript. "
        "Merge them into a single coherent outline in Markdown format. "
        "Use ## for section headings and - for bullet points. "
        f"Remove duplicates and organize by topic. {lang_inst}\n\n"
        f"{summaries}"
    )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Per-model prompt builders (translate / summarize / ocr)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

_FORMAT_INSTRUCTIONS = {
    "text": "Output only the translation, no explanations.",
    "srt": "Keep SRT format and timestamps unchanged. Output only the translated SRT.",
    "lrc": "Keep LRC timestamps [mm:ss.xx] unchanged. Output only the translated LRC.",
    "ass": "Keep ASS format, styles, and timestamps unchanged. Output only the translated ASS.",
    "markdown": "Preserve all Markdown formatting (headings, tables, lists, code blocks). Output only the translated Markdown.",
}


def _build_translate_user_prompt(text, source_lang, target_lang,
                                  format="text", style="colloquial", glossary=None):
    """Build the user-facing translation instruction (shared across builders)."""
    source_name = LANG_NAMES_EN.get(source_lang, source_lang)
    target_name = LANG_NAMES_EN.get(target_lang, target_lang)
    style_text = STYLE_INSTRUCTIONS.get(style, STYLE_INSTRUCTIONS["colloquial"])
    format_inst = _FORMAT_INSTRUCTIONS.get(format, _FORMAT_INSTRUCTIONS["text"])
    glossary_text = format_glossary(glossary)

    return (
        f"Translate the following {source_name} text to {target_name}.\n"
        f"Style: {style_text}\n"
        f"{format_inst}\n"
        f"{glossary_text}\n"
        f"{text}"
    ).strip()


def _build_summarize_user_prompt(text, source_lang=None):
    """Build summarize instruction with explicit language."""
    lang_name = LANG_NAMES_EN.get(source_lang, source_lang) if source_lang else None
    lang_inst = f"Write the summary in {lang_name}." if lang_name else "Write the summary in the same language as the text."
    return (
        f"Generate a bullet-point outline summary of the following transcript. "
        f"{lang_inst}\n\n"
        f"{text}"
    )


# ── Builder: default (supports system role) ──

def _translate_default(text, source_lang, target_lang, format, style, glossary):
    prompt = _build_translate_user_prompt(text, source_lang, target_lang, format, style, glossary)
    return {
        "mode": "chat",
        "messages": [
            {"role": "system", "content": "You are a professional translator."},
            {"role": "user", "content": prompt},
        ],
    }

def _summarize_default(text, source_lang=None):
    prompt = _build_summarize_user_prompt(text, source_lang)
    return {
        "mode": "chat",
        "messages": [
            {"role": "system", "content": "You are a professional text summarizer."},
            {"role": "user", "content": prompt},
        ],
    }

def _ocr_default(image_path, output_format="md", source_lang=None):
    messages = build_ocr_messages(image_path, format=output_format)
    return {"mode": "chat", "messages": messages}


# ── Builder: qwen3 (/no_think suffix) ──

def _translate_qwen3(text, source_lang, target_lang, format, style, glossary):
    prompt = _build_translate_user_prompt(text, source_lang, target_lang, format, style, glossary)
    return {
        "mode": "chat",
        "messages": [
            {"role": "system", "content": "You are a professional translator."},
            {"role": "user", "content": f"{prompt} /no_think"},
        ],
    }

def _summarize_qwen3(text, source_lang=None):
    prompt = _build_summarize_user_prompt(text, source_lang)
    return {
        "mode": "chat",
        "messages": [
            {"role": "system", "content": "You are a professional text summarizer."},
            {"role": "user", "content": f"{prompt} /no_think"},
        ],
    }

def _ocr_qwen3(image_path, output_format="md", source_lang=None):
    messages = build_ocr_messages(image_path, format=output_format)
    # Append /no_think to the last user message
    last = messages[-1]
    if isinstance(last["content"], list):
        last["content"].append({"type": "text", "text": "/no_think"})
    else:
        last["content"] += " /no_think"
    return {"mode": "chat", "messages": messages}


# ── Builder: gemma (no system role) ──

def _translate_gemma(text, source_lang, target_lang, format, style, glossary):
    prompt = _build_translate_user_prompt(text, source_lang, target_lang, format, style, glossary)
    return {
        "mode": "chat",
        "messages": [
            {"role": "user", "content": f"You are a professional translator. {prompt}"},
        ],
    }

def _summarize_gemma(text, source_lang=None):
    prompt = _build_summarize_user_prompt(text, source_lang)
    return {
        "mode": "chat",
        "messages": [
            {"role": "user", "content": f"You are a professional text summarizer. {prompt}"},
        ],
    }

def _ocr_gemma(image_path, output_format="md", source_lang=None):
    messages = build_ocr_messages(image_path, format=output_format)
    # Gemma: merge system into user
    if messages and messages[0]["role"] == "system":
        system_content = messages[0]["content"]
        messages = messages[1:]
        if messages and isinstance(messages[0]["content"], list):
            messages[0]["content"].insert(0, {"type": "text", "text": system_content + "\n\n"})
        elif messages:
            messages[0]["content"] = system_content + "\n\n" + messages[0]["content"]
    return {"mode": "chat", "messages": messages}


# ── Dispatch tables ──

_TRANSLATE_BUILDERS = {
    "default": _translate_default,
    "qwen3": _translate_qwen3,
    "qwen3.5": _translate_default,
    "gemma3": _translate_gemma,
    "gemma4": _translate_gemma,
    "gemma": _translate_gemma,
    "internvl2.5": _translate_default,
}

_SUMMARIZE_BUILDERS = {
    "default": _summarize_default,
    "qwen3": _summarize_qwen3,
    "gemma3": _summarize_gemma,
    "gemma4": _summarize_gemma,
    "gemma": _summarize_gemma,
}

_OCR_BUILDERS = {
    "default": _ocr_default,
    "qwen3": _ocr_qwen3,
    "qwen3vl": _ocr_qwen3,
    "qwen3.5": _ocr_qwen3,
    "gemma3": _ocr_gemma,
    "gemma4": _ocr_gemma,
    "gemma": _ocr_gemma,
}


def get_prompt_builder(task: str, model_family: str, thinking: bool = False):
    """Get the prompt builder function for a task + model combination.

    Args:
        task: "translate", "summarize", or "ocr"
        model_family: prompt builder key from inference config
        thinking: when True, skip /no_think for models that support thinking mode.
                  Output <think> blocks are always stripped by LlmWrapper.
    """
    # When thinking is enabled, Qwen3 should NOT add /no_think — use default builder
    if thinking and model_family in ("qwen3",):
        model_family = "default"

    tables = {
        "translate": _TRANSLATE_BUILDERS,
        "summarize": _SUMMARIZE_BUILDERS,
        "ocr": _OCR_BUILDERS,
    }
    task_builders = tables.get(task, {})
    return task_builders.get(model_family, task_builders.get("default", _translate_default))


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Video summary prompts (bullets / narrative)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

SUMMARY_MODE_BULLETS = "bullets"
SUMMARY_MODE_NARRATIVE = "narrative"

_PROMPT_BULLETS = """Below is a subtitle transcript. Every line is prefixed with a line number in the form [L<n>]:

{transcript}

Write a **hierarchical Markdown summary** of the transcript. Structure:

```
## {{H2 major theme}}
### {{H3 sub-theme — only when grouping helps}}
- **{{short label}}：** {{one-sentence description}} [L<first>-L<last>]
- **{{another label}}：** {{description}} [L<first>-L<last>]
    - {{optional nested sub-bullet — no line citation needed}}
```

Rules:
1. Use `##` for major themes (3~6 sections) and `###` for sub-themes when helpful
2. Every top-level bullet (line starting with `- **label：**`) MUST end with a line-number citation `[L<first>-L<last>]`, where `<first>` and `<last>` are the line numbers of the FIRST and LAST transcript lines that bullet covers. Copy the line numbers exactly as shown in the transcript (e.g. `[L12-L48]`). Do NOT write timestamps, do NOT write mm:ss, do NOT compute seconds — cite only line numbers. If a bullet covers a single line, cite `[L<n>-L<n>]`. Put the citation as a single bracket at the very end of the bullet with nothing after it — no period, no other punctuation — and do NOT split it into multiple comma-separated ranges.
3. Each top-level bullet should cover one coherent topic; do NOT micro-split a continuous topic into many short bullets — prefer fewer, substantive bullets over many fragmentary ones
4. Use bold labels at the start of each bullet (e.g., `**活動背景：**`); nested sub-bullets (indented 4 spaces) are optional and do NOT need a line citation
5. Every cited line number must be a line number that actually appears in the transcript above
6. Output Markdown only — no JSON, no code fences, no extra text
7. {language_directive}
"""

_PROMPT_NARRATIVE = """Below is a subtitle transcript. Every line is prefixed with a line number in the form [L<n>]:

{transcript}

Write a **flowing narrative summary** of the transcript as a sequence of prose paragraphs in chronological order.

Rules:
1. Divide the transcript into a handful of coherent paragraphs (aim for 3~6), each covering one continuous topic or scene; do NOT micro-split a continuous topic.
2. Each paragraph is plain prose — a few connected sentences. Do NOT use bullet points, headings, or bold labels.
3. Every paragraph MUST end with a line-number citation `[L<first>-L<last>]`, where `<first>` and `<last>` are the line numbers of the FIRST and LAST transcript lines that paragraph covers. Copy the line numbers exactly as shown in the transcript (e.g. `[L12-L48]`). Do NOT write timestamps, do NOT write mm:ss, do NOT compute seconds — cite only line numbers. Put the citation as a single bracket at the very end of the paragraph with nothing after it — no period, no other punctuation — and do NOT split it into multiple comma-separated ranges.
4. Separate paragraphs with a blank line.
5. Every cited line number must be a line number that actually appears in the transcript above.
6. Output prose only — no JSON, no code fences, no Markdown headings, no extra text.
7. {language_directive}
"""


def build_summary_prompt(
    transcript: str,
    output_language: Optional[str] = None,
    summary_mode: str = SUMMARY_MODE_BULLETS,
) -> str:
    """Build a video-summary prompt for the given mode.

    transcript: pre-formatted transcript lines (use format_transcript_numbered).
    summary_mode: "bullets" (hierarchical markdown) or "narrative" (prose paragraphs).
    output_language: ISO-ish code (e.g. "zh-TW", "en", "ja"); None -> match transcript.
    """
    if output_language:
        name = LANG_NAMES_EN.get(output_language, output_language)
        directive = (
            f'Write the summary in {name} (matching the transcript language).'
        )
    else:
        directive = (
            'Write the summary in the same language as the transcript above.'
        )
    tmpl = _PROMPT_NARRATIVE if summary_mode == SUMMARY_MODE_NARRATIVE else _PROMPT_BULLETS
    return tmpl.format(transcript=transcript, language_directive=directive)
