"""Tests for local translate prompt builders (keep_names threading)."""
import pytest
from app.utils.prompts import get_prompt_builder


def _text(builder_result) -> str:
    """Concatenate all message contents from a chat-dict builder result."""
    return " ".join(m["content"] for m in builder_result["messages"])


# ── keep_names=True: name instruction must appear ──

def test_local_translate_builder_keep_names_true_includes_name_instruction():
    builder = get_prompt_builder("translate", "qwen3")
    result = builder("1\n00:00:01,000 --> 00:00:02,000\nHello John\n", "en", "zh-TW", "srt", "colloquial", None, True)
    text = _text(result)
    assert "name" in text.lower() or "proper noun" in text.lower(), (
        f"Expected name-keeping instruction in output, got: {text!r}"
    )


# ── keep_names=False or omitted: name instruction must NOT appear ──

def test_local_translate_builder_keep_names_false_or_omitted_has_no_name_instruction():
    builder = get_prompt_builder("translate", "qwen3")
    text_omitted = _text(builder("chunk text", "en", "zh-TW", "txt", "colloquial", None))
    text_false   = _text(builder("chunk text", "en", "zh-TW", "txt", "colloquial", None, False))
    for label, t in (("omitted", text_omitted), ("False", text_false)):
        assert not ("keep" in t.lower() and "name" in t.lower()), (
            f"Unexpected name-keeping instruction when keep_names={label}: {t!r}"
        )


# ── Same contract holds for the other two builder families ──

def test_local_translate_builder_default_keep_names_true():
    builder = get_prompt_builder("translate", "default")
    text = _text(builder("Some text.", "en", "zh-TW", "txt", "colloquial", None, True))
    assert "name" in text.lower() or "proper noun" in text.lower()


def test_local_translate_builder_default_keep_names_false():
    builder = get_prompt_builder("translate", "default")
    text = _text(builder("Some text.", "en", "zh-TW", "txt", "colloquial", None, False))
    assert not ("keep" in text.lower() and "name" in text.lower())


def test_local_translate_builder_gemma_keep_names_true():
    builder = get_prompt_builder("translate", "gemma3")
    text = _text(builder("Some text.", "en", "zh-TW", "txt", "colloquial", None, True))
    assert "name" in text.lower() or "proper noun" in text.lower()


def test_local_translate_builder_gemma_keep_names_false():
    builder = get_prompt_builder("translate", "gemma3")
    text = _text(builder("Some text.", "en", "zh-TW", "txt", "colloquial", None, False))
    assert not ("keep" in text.lower() and "name" in text.lower())
