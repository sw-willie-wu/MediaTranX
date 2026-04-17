"""Pure text chunking helpers.

Splits long text on sentence/paragraph boundaries for translation or
context-window-bounded inference. No domain or engine dependencies.
"""
from __future__ import annotations
import re


# Rough estimate: 1 token ≈ 3.5 characters for mixed CJK/English text
_CHARS_PER_TOKEN = 3.5


def split_by_sentences(text: str, max_chars: int) -> list[str]:
    """Split text on sentence boundaries."""
    sentences = re.split(r'(?<=[。！？.!?\n])\s*', text)
    chunks: list[str] = []
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

    chunks: list[str] = []
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


def split_text_for_context(text: str, max_tokens: int = 3000) -> list[str]:
    """Split text into chunks that fit within a token budget.

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
