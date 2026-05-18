"""Plain-text chunked translation (document-only).

Sibling to `translate_service.py`. Lives here because it has a single consumer.
SRT-batch translation (shared by 4 services) lives in `app/pipeline/translate.py`.

Audit v3 §5.2 originally proposed a `services/document/translate/` subpackage
(service.py + text.py). Kept as a sibling module for now to avoid moving the
existing `translate_service.py`; the full subpackage restructure can happen later.
"""
from __future__ import annotations

import logging
from typing import Callable, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from app.adapters.ai.remote.base import RemoteProvider
    from app.services.llm.chat_service import ChatSession

logger = logging.getLogger(__name__)


def _get_cloud_text_chunk_size(prov, model: str = "") -> int:
    """Get plain-text translation chunk size (in characters) based on provider context."""
    from app.pipeline.translate import get_cloud_ctx

    n_ctx = get_cloud_ctx(prov, model)
    # Reserve half for output, ~2 chars per token
    return max(1000, (n_ctx // 4) * 2)


def translate_text_cloud(
    text: str,
    source_lang: str,
    target_lang: str,
    prov: "RemoteProvider",
    model: str,
    on_progress: Optional[Callable[[float, str], None]] = None,
    max_chars: Optional[int] = None,
    glossary: Optional[dict[str, str]] = None,
) -> str:
    """Chunked plain-text translation (cloud)."""
    from app.adapters.ai.inference_config import get_remote_inference_config
    from app.utils.prompts import build_translate_prompt
    from app.utils.text_chunking import split_text

    remote_config = get_remote_inference_config("translate")

    if max_chars is None:
        max_chars = _get_cloud_text_chunk_size(prov, model)
    chunks = split_text(text, max_chars=max_chars)
    total = len(chunks)
    logger.info(f"translate_text_cloud: {len(text)} chars, max_chars={max_chars}, chunks={total}")
    translated_chunks = []

    for i, chunk in enumerate(chunks):
        if on_progress:
            if total == 1:
                on_progress(0.05, "task.progress.translating")
            else:
                on_progress(i / total, f"task.progress.translating_segment|{i + 1}|{total}")

        prompt = build_translate_prompt(chunk, source_lang, target_lang, glossary=glossary)
        messages = [
            {"role": "system", "content": "You are a professional translator."},
            {"role": "user", "content": prompt},
        ]
        max_tokens = min(max(len(chunk) * 4, 100), remote_config["max_tokens"])
        result = prov.chat(
            model=model, messages=messages,
            max_tokens=max_tokens, temperature=remote_config["temperature"],
        )
        translated_chunks.append(result)

        if on_progress:
            progress = min((i + 1) / total, 1.0)
            on_progress(progress, f"task.progress.translated_segment|{i + 1}|{total}")

    return "\n\n".join(translated_chunks)


def translate_text_local(
    text: str,
    source_lang: str,
    target_lang: str,
    session: "ChatSession",
    on_progress: Optional[Callable[[float, str], None]] = None,
    max_chars: Optional[int] = None,
    glossary: Optional[dict[str, str]] = None,
    model_family: str = "gemma4",
    model_size: str = "4b",
    style: str = "colloquial",
    format: str = "text",
) -> str:
    """Chunked plain-text translation (local LLM). Must be called within a `chat_service.session()` block."""
    from app.adapters.ai.inference_config import get_inference_config
    from app.utils.inference import (
        calc_max_tokens,
        estimate_tokens,
        fake_progress,
    )
    from app.utils.prompts import get_prompt_builder
    from app.utils.text_chunking import split_text

    config = get_inference_config(model_family, model_size, "translate")
    builder = get_prompt_builder("translate", config["prompt_builder"], thinking=config.get("thinking", False))
    n_ctx = config["n_ctx"]

    # Auto-calculate chunk size from model capacity if not specified
    if max_chars is None:
        chunk_tokens = n_ctx // 3  # Reserve 2/3 for output + prompt overhead
        max_chars = int(chunk_tokens * 3.5)

    chunks = split_text(text, max_chars=max_chars)
    total = len(chunks)
    logger.info(f"translate_text_local: {len(text)} chars, max_chars={max_chars}, chunks={total}")
    translated_chunks = []

    for i, chunk in enumerate(chunks):
        result = builder(chunk, source_lang, target_lang, format, style, glossary)
        input_tokens = estimate_tokens(chunk)
        max_tokens = calc_max_tokens(config, n_ctx, input_tokens)

        chunk_start_pct = i / total
        chunk_end_pct = (i + 1) / total

        with fake_progress(on_progress, chunk_start_pct, chunk_end_pct,
                           f"task.progress.translating_segment|{i + 1}|{total}",
                           cancellable=session):
            if result["mode"] == "chat":
                output = session.chat(
                    messages=result["messages"], max_tokens=max_tokens,
                    temperature=config["temperature"],
                    top_k=config.get("top_k", 40), top_p=config.get("top_p", 0.9),
                )
            else:
                output = session.complete(
                    prompt=result["prompt"], max_tokens=max_tokens,
                    temperature=config["temperature"],
                    top_k=config.get("top_k", 40), top_p=config.get("top_p", 0.9),
                )
        translated_chunks.append(output)

        if on_progress:
            on_progress(chunk_end_pct, f"task.progress.translating_segment|{i + 1}|{total}")

    return "\n\n".join(translated_chunks)
