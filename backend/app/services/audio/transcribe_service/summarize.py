"""
Map-Reduce summarization utility.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Short text is summarized directly; long text is split, summarized per chunk,
then merged. Supports cloud and local LLMs via chat_fn abstraction.
"""
from __future__ import annotations

import logging
from typing import Callable, Optional

logger = logging.getLogger(__name__)


def map_reduce_summarize(
    full_text: str,
    chat_fn: Callable[[str, int], str],
    max_tokens_per_chunk: int,
    on_progress: Optional[Callable[[float, str], None]] = None,
    model_family: str = "default",
    source_lang: Optional[str] = None,
    cancellable=None,
) -> str:
    """
    Map-reduce summarization.

    Args:
        full_text: The full text to summarize
        chat_fn: LLM call function (prompt, max_tokens) -> str
        on_progress: Progress callback (0.0~1.0, message)
        max_tokens_per_chunk: Maximum tokens per chunk
        model_family: Model family for prompt builder (for future use)
        source_lang: Source language code for explicit language instruction

    Returns:
        Summary text.
    """
    from app.utils.prompts import (
        build_summarize_prompt,
        build_chunk_summarize_prompt,
        build_merge_summaries_prompt,
    )
    from app.utils.text_chunking import split_text_for_context

    chunks = split_text_for_context(full_text, max_tokens=max_tokens_per_chunk)
    logger.info(f"map_reduce_summarize: {len(full_text)} chars, chunks={len(chunks)}")

    from app.utils.inference import fake_progress

    if len(chunks) == 1:
        with fake_progress(on_progress, 0.1, 0.95, "task.progress.generating_summary",
                           cancellable=cancellable):
            return chat_fn(build_summarize_prompt(full_text, source_lang), 2048)

    # Map: summarize each chunk independently
    chunk_summaries = []
    for ci, chunk in enumerate(chunks):
        start_pct = 0.1 + 0.7 * (ci / len(chunks))
        end_pct = 0.1 + 0.7 * ((ci + 1) / len(chunks))
        with fake_progress(on_progress, start_pct, end_pct,
                           f"task.progress.summarizing_chunk|{ci + 1}|{len(chunks)}",
                           cancellable=cancellable):
            chunk_summaries.append(chat_fn(build_chunk_summarize_prompt(chunk, source_lang), 1024).strip())

    # Reduce: merge summaries
    with fake_progress(on_progress, 0.85, 0.95, "task.progress.merging_summary",
                       cancellable=cancellable):
        merged = "\n\n".join(chunk_summaries)
        return chat_fn(build_merge_summaries_prompt(merged, source_lang), 2048)


def calc_chunk_budget(
    n_ctx: int,
    *,
    output_cap: int = 0,
    prompt_overhead: int = 200,
    min_tokens: int = 500,
) -> int:
    """Conservative per-chunk token budget for map-reduce summarization.

    Leaves roughly half of n_ctx for model output; subtracts fixed prompt
    overhead. Clamped to at least `min_tokens`. If `output_cap > 0`, budget
    is capped at that value.
    """
    budget = n_ctx // 2 - prompt_overhead
    if output_cap:
        budget = min(budget, output_cap)
    return max(min_tokens, budget)
