"""
Map-Reduce 摘要工具
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
短文本直接摘要，長文本分段摘要再合併。
支援雲端和本地 LLM，透過 chat_fn 抽象。
"""
from __future__ import annotations

import logging
from typing import Callable, Optional

logger = logging.getLogger(__name__)


def map_reduce_summarize(
    full_text: str,
    chat_fn: Callable[[str, int], str],
    on_progress: Optional[Callable[[float, str], None]] = None,
    max_tokens_per_chunk: int = 2000,
) -> str:
    """
    Map-reduce 摘要。

    Args:
        full_text: 要摘要的完整文本
        chat_fn: (prompt, max_tokens) -> str 的 LLM 呼叫函式
        on_progress: 進度回調 (0.0~1.0, message)
        max_tokens_per_chunk: 每段最大 token 數

    Returns:
        摘要文字
    """
    from app.utils.prompts import (
        build_summarize_prompt,
        build_chunk_summarize_prompt,
        build_merge_summaries_prompt,
        split_text_for_context,
    )

    chunks = split_text_for_context(full_text, max_tokens=max_tokens_per_chunk)
    logger.info(f"map_reduce_summarize: {len(full_text)} chars, chunks={len(chunks)}")

    if len(chunks) == 1:
        if on_progress:
            on_progress(0.1, "生成摘要...")
        return chat_fn(build_summarize_prompt(full_text), 2048)

    # Map: 各段獨立摘要
    chunk_summaries = []
    for ci, chunk in enumerate(chunks):
        if on_progress:
            on_progress(0.1 + 0.7 * (ci / len(chunks)), f"摘要分段 {ci + 1}/{len(chunks)}...")
        chunk_summaries.append(chat_fn(build_chunk_summarize_prompt(chunk), 1024).strip())

    # Reduce: 合併
    if on_progress:
        on_progress(0.85, "合併摘要...")
    merged = "\n\n".join(chunk_summaries)
    return chat_fn(build_merge_summaries_prompt(merged), 2048)
