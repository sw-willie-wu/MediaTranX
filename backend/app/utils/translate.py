"""
Batch translation utility functions.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Provides SRT-format batch translation, shared across services.
Supports both cloud (RemoteProvider) and local (LlamaServerRuntime) backends.

All translations use SRT format (aligned by index, more stable than line-split).
"""
from __future__ import annotations

import logging
from typing import Callable, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from app.engine.ai.remote.base import RemoteProvider

logger = logging.getLogger(__name__)

# Estimated max input tokens per cloud batch (including prompt overhead, buffer for output)
# Rough estimate: 1 token ~ 4 chars (English) / 1.5 chars (CJK), using conservative 2 chars/token
_CLOUD_MAX_INPUT_TOKENS = {
    "ollama":  3000,    # Ollama models typically have 4K~8K context
    "default": 30000,   # OpenAI 128K / Gemini 1M, large buffer for output
}


def _calc_cloud_srt_batch_size(prov, seg_dicts: list[dict]) -> int:
    """Dynamically calculate SRT batch size based on provider and segment content."""
    provider_name = type(prov).__name__.lower().replace("provider", "")
    max_tokens = _CLOUD_MAX_INPUT_TOKENS.get(provider_name, _CLOUD_MAX_INPUT_TOKENS["default"])
    logger.debug(f"Cloud batch calc: provider={provider_name}, max_tokens={max_tokens}, segments={len(seg_dicts)}")

    if not seg_dicts:
        return 1

    # Estimate average tokens per segment
    sample = seg_dicts[:20]  # Sample first 20 segments
    avg_chars = sum(len(s.get("text", "")) for s in sample) / len(sample)
    # SRT format overhead per segment: index + timecode ~ 40 chars
    avg_tokens_per_seg = int((avg_chars + 40) / 2)

    if avg_tokens_per_seg <= 0:
        return len(seg_dicts)

    # Prompt template overhead ~ 500 tokens
    batch_size = max(1, (max_tokens - 500) // avg_tokens_per_seg)
    # Cap: do not exceed total segment count
    result = min(batch_size, len(seg_dicts))
    logger.info(f"Cloud SRT batch_size={result} (avg_tokens/seg={avg_tokens_per_seg})")
    return result


def _get_cloud_text_chunk_size(prov) -> int:
    """Get plain-text translation chunk size (in characters) based on provider."""
    provider_name = type(prov).__name__.lower().replace("provider", "")
    max_tokens = _CLOUD_MAX_INPUT_TOKENS.get(provider_name, _CLOUD_MAX_INPUT_TOKENS["default"])
    # Reserve half for output, multiply by 2 chars/token
    return max(1000, (max_tokens // 2) * 2)


def get_cloud_provider(
    provider: str,
    conn_id: Optional[int],
    remote_model: str,
) -> "RemoteProvider":
    """Get a cloud provider instance."""
    from app.init.container import get_container
    prov = get_container().remote_service().get_provider_for_connection(conn_id, provider)
    if prov is None:
        raise RuntimeError(f"No available {provider} connection found")
    return prov


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
    """
    Chunked plain-text translation (cloud). Suitable for OCR results,
    documents, and other text without timestamps.

    Returns:
        The fully translated text.
    """
    from app.utils.inference import get_remote_inference_config
    from app.utils.prompts import build_translate_prompt, split_text

    remote_config = get_remote_inference_config("translate")

    if max_chars is None:
        max_chars = _get_cloud_text_chunk_size(prov)
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
    runtime,
    on_progress: Optional[Callable[[float, str], None]] = None,
    max_chars: Optional[int] = None,
    glossary: Optional[dict[str, str]] = None,
    model_family: str = "gemma4",
    model_size: str = "4b",
    style: str = "colloquial",
    format: str = "text",
) -> str:
    """
    Chunked plain-text translation (local LLM). Must be called within
    a runtime.acquire() context.

    Returns:
        The fully translated text.
    """
    from app.utils.inference import get_inference_config, calc_max_tokens, estimate_tokens
    from app.utils.prompts import get_prompt_builder, split_text

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

        if result["mode"] == "chat":
            output = runtime.chat(
                messages=result["messages"], max_tokens=max_tokens,
                temperature=config["temperature"],
                top_k=config.get("top_k", 40), top_p=config.get("top_p", 0.9),
            )
        else:
            output = runtime.complete(
                prompt=result["prompt"], max_tokens=max_tokens,
                temperature=config["temperature"],
                top_k=config.get("top_k", 40), top_p=config.get("top_p", 0.9),
            )
        translated_chunks.append(output)

        if on_progress:
            progress = min((i + 1) / total, 1.0)
            on_progress(progress, f"task.progress.translating_segment|{i + 1}|{total}")

    return "\n\n".join(translated_chunks)


def translate_srt_cloud(
    seg_dicts: list[dict],
    source_lang: str,
    target_lang: str,
    prov: "RemoteProvider",
    model: str,
    on_progress: Optional[Callable[[float, str], None]] = None,
    batch_size: Optional[int] = None,
    keep_names: bool = True,
    style: str = "colloquial",
    glossary: Optional[dict[str, str]] = None,
) -> list[dict]:
    """
    Cloud SRT batch translation.

    Args:
        seg_dicts: [{"start": float, "end": float, "text": str}, ...]
        prov: RemoteProvider instance
        model: Cloud model ID

    Returns:
        Translated seg_dicts list.
    """
    from app.utils.inference import get_remote_inference_config
    from app.utils.prompts import build_srt_translate_prompt, segments_to_srt, parse_srt_response

    remote_config = get_remote_inference_config("translate")

    if batch_size is None:
        batch_size = _calc_cloud_srt_batch_size(prov, seg_dicts)

    total = len(seg_dicts)
    num_batches = (total + batch_size - 1) // batch_size
    logger.info(f"translate_srt_cloud: {total} segments, batch_size={batch_size}, batches={num_batches}")
    translated_all = []

    for batch_idx in range(num_batches):
        start = batch_idx * batch_size
        end = min(start + batch_size, total)
        batch = seg_dicts[start:end]

        if on_progress:
            if num_batches == 1:
                on_progress(0.05, f"task.progress.translating_total|{total}")
            else:
                on_progress(batch_idx / num_batches, f"task.progress.translating_segment|{start}|{total}")

        srt_text = segments_to_srt(batch, start_index=start + 1)
        prompt = build_srt_translate_prompt(
            srt_text, source_lang, target_lang,
            keep_names=keep_names, style=style, glossary=glossary,
        )
        messages = [
            {"role": "system", "content": "You are a professional subtitle translator."},
            {"role": "user", "content": prompt},
        ]
        max_tokens = min(len(srt_text) * 3, remote_config["max_tokens"])
        translated_srt = prov.chat(
            model=model, messages=messages,
            max_tokens=max_tokens, temperature=remote_config["temperature"],
        )

        batch_translated = parse_srt_response(translated_srt, batch)
        translated_all.extend(batch_translated)

        if on_progress:
            progress = min((batch_idx + 1) / num_batches, 1.0)
            on_progress(progress, f"task.progress.translated_segment|{end}|{total}")

    return translated_all


def translate_srt_local(
    seg_dicts: list[dict],
    source_lang: str,
    target_lang: str,
    runtime,
    on_progress: Optional[Callable[[float, str], None]] = None,
    batch_size: Optional[int] = None,
    keep_names: bool = True,
    style: str = "colloquial",
    glossary: Optional[dict[str, str]] = None,
    model_family: str = "gemma4",
    model_size: str = "4b",
) -> list[dict]:
    """
    Local LLM SRT batch translation (must be called within runtime.acquire() context).

    Args:
        seg_dicts: [{"start": float, "end": float, "text": str}, ...]
        runtime: An acquired LlamaServerRuntime instance
        model_family: Model family for inference config
        model_size: Model size variant (e.g. "4b", "12b")

    Returns:
        Translated seg_dicts list.
    """
    from app.utils.inference import get_inference_config, calc_max_tokens, calc_batch_size, estimate_tokens
    from app.utils.prompts import get_prompt_builder, segments_to_srt, parse_srt_response

    config = get_inference_config(model_family, model_size, "translate")
    builder = get_prompt_builder("translate", config["prompt_builder"], thinking=config.get("thinking", False))
    n_ctx = config["n_ctx"]

    # Auto batch size if not specified
    if batch_size is None:
        avg_seg_tokens = sum(estimate_tokens(s["text"]) for s in seg_dicts) // max(1, len(seg_dicts))
        batch_size = calc_batch_size(n_ctx, n_ctx // 3, 200, max(1, avg_seg_tokens))

    total = len(seg_dicts)
    num_batches = (total + batch_size - 1) // batch_size
    logger.info(f"translate_srt_local: {total} segments, batch_size={batch_size}, batches={num_batches}")
    translated_all = []

    for batch_idx in range(num_batches):
        start = batch_idx * batch_size
        end = min(start + batch_size, total)
        batch = seg_dicts[start:end]

        srt_text = segments_to_srt(batch, start_index=start + 1)
        result = builder(srt_text, source_lang, target_lang, "srt", style, glossary)
        input_tokens = estimate_tokens(srt_text)
        max_tokens = calc_max_tokens(config, n_ctx, input_tokens)

        if result["mode"] == "chat":
            translated_srt = runtime.chat(
                messages=result["messages"], max_tokens=max_tokens,
                temperature=config["temperature"],
                top_k=config.get("top_k", 40), top_p=config.get("top_p", 0.9),
            )
        else:
            translated_srt = runtime.complete(
                prompt=result["prompt"], max_tokens=max_tokens,
                temperature=config["temperature"],
                top_k=config.get("top_k", 40), top_p=config.get("top_p", 0.9),
            )

        batch_translated = parse_srt_response(translated_srt, batch)
        translated_all.extend(batch_translated)

        if on_progress:
            progress = min((batch_idx + 1) / num_batches, 1.0)
            on_progress(progress, f"task.progress.translated_segment|{end}|{total}")

    return translated_all
