"""Cross-service SRT batch translation orchestration.

Supports both cloud (RemoteProvider) and local (LlmWrapper) backends.
All translations use SRT format (aligned by index, more stable than line-split).

Plain-text translation (document-only) lives in
`services/document/translate_service/text.py` since it has a single consumer.

`get_cloud_provider` remains here temporarily and is scheduled for removal
after Wave 4 §2.4 (services inject RemoteService directly).
"""
from __future__ import annotations

import logging
from typing import Callable, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from app.adapters.ai.remote.base import RemoteProvider

logger = logging.getLogger(__name__)

# Default context sizes for cloud providers (used when actual ctx is unknown)
_CLOUD_DEFAULT_CTX = {
    "ollama":  8192,     # Ollama models typically 4K~32K, query via /api/show for actual
    "default": 128000,   # OpenAI 128K / Gemini 1M
}


def _calc_srt_batch_size(n_ctx: int, seg_dicts: list[dict], max_batch: int = 0) -> int:
    """Calculate SRT translation batch size from context window and segment content.

    Shared by both local and cloud translation paths.
    """
    if not seg_dicts:
        return 1

    from app.utils.inference import estimate_tokens

    # Estimate average tokens per segment (sample first 20)
    sample = seg_dicts[:20]
    avg_text_tokens = sum(estimate_tokens(s.get("text", "")) for s in sample) // len(sample)
    # SRT format overhead per segment: index + timestamp + blank line ≈ 13 tokens
    avg_seg_tokens = max(1, avg_text_tokens + 13)

    # Each segment appears in both input AND output (translation ≈ same length)
    # Total per segment ≈ input + output = 2 × avg_seg_tokens
    # Conservative: 50% utilization to absorb token estimation error + prompt overhead
    tokens_per_seg = avg_seg_tokens * 2
    batch_size = max(1, n_ctx // 2 // tokens_per_seg)

    if max_batch > 0:
        batch_size = min(batch_size, max_batch)

    result = min(batch_size, len(seg_dicts))
    logger.info(f"SRT batch_size={result} (n_ctx={n_ctx}, avg_seg_tokens={avg_seg_tokens}, segs={len(seg_dicts)})")
    return result


def get_cloud_ctx(prov, model: str = "") -> int:
    """Get context window size for a cloud provider."""
    provider_name = type(prov).__name__.lower().replace("provider", "")
    if provider_name == "ollama":
        # Query actual model context via /api/show
        try:
            return prov.get_model_ctx(model)
        except Exception:
            pass
    return _CLOUD_DEFAULT_CTX.get(provider_name, _CLOUD_DEFAULT_CTX["default"])


def get_cloud_provider(
    provider: str,
    conn_id: Optional[int],
    remote_model: str,
) -> "RemoteProvider":
    """Get a cloud provider instance. TEMPORARY: removed after Wave 4 §2.4."""
    from app.init.container import get_container
    prov = get_container().remote_service().get_provider_for_connection(conn_id, provider)
    if prov is None:
        raise RuntimeError(f"No available {provider} connection found")
    return prov


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
    """Cloud SRT batch translation."""
    from app.adapters.ai.inference_config import get_remote_inference_config
    from app.utils.prompts import build_srt_translate_prompt
    from app.utils.subtitles import segments_to_srt, parse_srt_response

    remote_config = get_remote_inference_config("translate")

    if batch_size is None:
        n_ctx = get_cloud_ctx(prov, model)
        batch_size = _calc_srt_batch_size(n_ctx, seg_dicts)

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


def translate_srt_auto(
    seg_dicts: list[dict],
    source_lang: str,
    target_lang: str,
    *,
    remote: bool = False,
    on_progress: Optional[Callable[[float, str], None]] = None,
    # Remote-only
    provider: str = "",
    conn_id: Optional[int] = None,
    remote_model: str = "",
    # Local-only
    model_family: str = "gemma4",
    model_size: str = "4b",
    quantization: Optional[str] = None,
    # Common
    keep_names: bool = True,
    style: str = "colloquial",
    glossary: Optional[dict[str, str]] = None,
    # Progress keys (local path only; overridable for per-service naming)
    load_msg: str = "task.progress.load_translate_model",
    start_msg: str = "task.progress.start_translate",
) -> list[dict]:
    """Unified local/remote SRT translation dispatch.

    Collapses the 4-service-copied boilerplate (cloud provider fetch + acquire +
    0.05/0.95 progress split + translate_srt_{cloud,local}). Caller pre-shapes
    progress via `on_progress` (e.g. stage_progress callback).

    Progress layout (when `on_progress` provided):
    - Remote: translate_srt_cloud spans the full 0..1 range.
    - Local: 0.0 → 0.05 for runtime.acquire (model load), 0.05 → 1.0 for translation.
    """
    if remote:
        prov = get_cloud_provider(provider, conn_id, remote_model)
        return translate_srt_cloud(
            seg_dicts, source_lang, target_lang, prov, remote_model,
            on_progress=on_progress,
            keep_names=keep_names, style=style, glossary=glossary,
        )

    from app.init.container import get_container

    variant = f"{model_size}:{quantization}" if quantization else model_size
    runtime = get_container().llama_runtime()

    if on_progress:
        on_progress(0.0, load_msg)

    with runtime.acquire(
        model_family,
        variant,
        lambda p, m: on_progress(p * 0.05, m) if on_progress else None,
    ):
        if on_progress:
            on_progress(0.05, start_msg)
        return translate_srt_local(
            seg_dicts, source_lang, target_lang, runtime,
            on_progress=lambda p, m: on_progress(0.05 + p * 0.95, m) if on_progress else None,
            keep_names=keep_names, style=style, glossary=glossary,
            model_family=model_family, model_size=model_size,
        )


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
    """Local LLM SRT batch translation (must be called within runtime.acquire() context)."""
    from app.adapters.ai.inference_config import get_inference_config
    from app.utils.inference import (
        calc_max_tokens,
        estimate_tokens,
        fake_progress,
    )
    from app.utils.prompts import get_prompt_builder
    from app.utils.subtitles import segments_to_srt, parse_srt_response

    config = get_inference_config(model_family, model_size, "translate")
    builder = get_prompt_builder("translate", config["prompt_builder"], thinking=config.get("thinking", False))
    n_ctx = config["n_ctx"]

    # Auto batch size if not specified
    if batch_size is None:
        max_batch = config.get("max_srt_batch", 0)
        batch_size = _calc_srt_batch_size(n_ctx, seg_dicts, max_batch=max_batch)

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

        batch_start_pct = batch_idx / num_batches
        batch_end_pct = (batch_idx + 1) / num_batches

        with fake_progress(on_progress, batch_start_pct, batch_end_pct,
                           f"task.progress.translating_segment|{start + 1}|{total}",
                           runtime=runtime):
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
