"""Tests for app.utils.text_chunking — pure functions."""
from __future__ import annotations

import pytest

from app.utils.text_chunking import (
    split_by_sentences,
    split_text,
    split_text_for_context,
    _CHARS_PER_TOKEN,
)


class TestSplitBySentences:
    def test_empty_returns_empty(self):
        assert split_by_sentences("", max_chars=100) == []

    def test_single_short_sentence_returns_single_chunk(self):
        assert split_by_sentences("Hello world.", max_chars=100) == ["Hello world."]

    def test_two_short_sentences_merged(self):
        result = split_by_sentences("Hi. There.", max_chars=100)
        assert len(result) == 1
        assert "Hi." in result[0]
        assert "There." in result[0]

    def test_chinese_sentence_endings(self):
        """Splits on 。！？ (full-width CJK punctuation) too."""
        text = "你好。世界！再見？"
        result = split_by_sentences(text, max_chars=100)
        assert len(result) == 1
        assert "你好" in result[0] and "世界" in result[0]

    def test_splits_when_max_chars_exceeded(self):
        """When merging two sentences would exceed max_chars, emit current chunk."""
        a = "A" * 50 + "."
        b = "B" * 50 + "."
        result = split_by_sentences(f"{a} {b}", max_chars=60)
        assert len(result) == 2
        assert result[0].rstrip().endswith(a)
        assert result[1].rstrip().endswith(b)

    def test_newline_boundary(self):
        """Newline triggers sentence-boundary split per regex."""
        result = split_by_sentences("Line one\nLine two\n", max_chars=10)
        assert len(result) == 2


class TestSplitText:
    def test_short_returns_single(self):
        text = "Short text."
        assert split_text(text, max_chars=1500) == [text]

    def test_long_text_splits_on_paragraphs(self):
        para1 = "P1 " * 200  # ~600 chars
        para2 = "P2 " * 200
        text = f"{para1}\n\n{para2}"
        result = split_text(text, max_chars=1000)
        assert len(result) == 2
        assert "P1" in result[0]
        assert "P2" in result[1]

    def test_short_paragraphs_merged_under_limit(self):
        text = "Para one.\n\nPara two.\n\nPara three."
        result = split_text(text, max_chars=1500)
        assert len(result) == 1
        for marker in ("Para one", "Para two", "Para three"):
            assert marker in result[0]

    def test_oversized_paragraph_falls_back_to_sentence_split(self):
        """A subsequent oversized paragraph falls back to sentence-split.

        Quirk: split_text's fallback only fires inside the loop's else branch —
        the FIRST paragraph always goes into current_chunk without sizing check.
        So a leading tiny paragraph is required to trigger fallback on the
        second oversized one.
        """
        long_para = " ".join(f"Sentence {i}." for i in range(50))
        text = f"short.\n\n{long_para}"
        result = split_text(text, max_chars=100)
        assert len(result) > 2  # leading "short." chunk + multiple sentence chunks
        joined = " ".join(result)
        assert "Sentence 0" in joined
        assert "Sentence 49" in joined


class TestSplitTextForContext:
    def test_token_to_char_conversion(self):
        """max_tokens → max_chars uses _CHARS_PER_TOKEN multiplier."""
        text = "x" * 50
        # 50 chars / 3.5 chars-per-token = ~14 tokens; budget 100 tokens easily fits
        result = split_text_for_context(text, max_tokens=100)
        assert result == [text]

    def test_under_budget_returns_single(self):
        text = "short"
        result = split_text_for_context(text, max_tokens=3000)
        assert result == [text]

    def test_over_budget_splits_on_newlines(self):
        """Splits paragraphs separated by single \\n (NOT \\n\\n like split_text)."""
        max_tokens = 10  # max_chars = int(10 * 3.5) = 35
        text = "Line A line A line A\nLine B line B line B\nLine C line C line C"
        result = split_text_for_context(text, max_tokens=max_tokens)
        assert len(result) > 1
        joined = "\n".join(result)
        assert "Line A" in joined and "Line C" in joined

    def test_chars_per_token_constant_unchanged(self):
        """Defensive: catches accidental tuning of the rough estimate."""
        assert _CHARS_PER_TOKEN == 3.5
