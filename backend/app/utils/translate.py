"""
批次翻譯工具函式
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
提供 SRT 格式批次翻譯，供各 service 共用。
支援雲端（RemoteProvider）和本地（LlamaServerRuntime）兩種後端。

所有翻譯統一使用 SRT 格式（靠編號對齊，比逐行 split 更穩定）。
"""
from __future__ import annotations

import logging
from typing import Callable, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from app.engine.ai.remote.base import RemoteProvider

logger = logging.getLogger(__name__)

# 本地 LLM：context window 小（~8K），分小批
LOCAL_BATCH_SIZE = 5
LOCAL_TEXT_CHUNK_SIZE = 1500

# 雲端每批最大 token 數估算（含 prompt 開銷，留 buffer 給 output）
# 粗估：1 token ≈ 4 chars (英文) / 1.5 chars (CJK)，取保守值 2 chars/token
_CLOUD_MAX_INPUT_TOKENS = {
    "ollama":  3000,    # Ollama 模型通常 4K~8K context
    "default": 30000,   # OpenAI 128K / Gemini 1M，留大量 buffer 給 output
}


def _estimate_tokens(text: str) -> int:
    """粗估 token 數（保守：2 chars/token）"""
    return len(text) // 2


def _calc_cloud_srt_batch_size(prov, seg_dicts: list[dict]) -> int:
    """根據 provider 和段落內容動態計算 SRT 批次大小"""
    provider_name = type(prov).__name__.lower().replace("provider", "")
    max_tokens = _CLOUD_MAX_INPUT_TOKENS.get(provider_name, _CLOUD_MAX_INPUT_TOKENS["default"])
    logger.debug(f"Cloud batch calc: provider={provider_name}, max_tokens={max_tokens}, segments={len(seg_dicts)}")

    if not seg_dicts:
        return 1

    # 估算平均每段的 token 數
    sample = seg_dicts[:20]  # 取前 20 段估算
    avg_chars = sum(len(s.get("text", "")) for s in sample) / len(sample)
    # SRT 格式每段額外開銷：編號 + 時間軸 ≈ 40 chars
    avg_tokens_per_seg = int((avg_chars + 40) / 2)

    if avg_tokens_per_seg <= 0:
        return len(seg_dicts)

    # prompt 模板開銷 ≈ 500 tokens
    batch_size = max(1, (max_tokens - 500) // avg_tokens_per_seg)
    # 上限：不超過總段數
    result = min(batch_size, len(seg_dicts))
    logger.info(f"Cloud SRT batch_size={result} (avg_tokens/seg={avg_tokens_per_seg})")
    return result


def _get_cloud_text_chunk_size(prov) -> int:
    """根據 provider 取得純文字翻譯的 chunk 大小（字元數）"""
    provider_name = type(prov).__name__.lower().replace("provider", "")
    max_tokens = _CLOUD_MAX_INPUT_TOKENS.get(provider_name, _CLOUD_MAX_INPUT_TOKENS["default"])
    # 留一半給 output，再乘 2 chars/token
    return max(1000, (max_tokens // 2) * 2)


def get_cloud_provider(
    provider: str,
    conn_id: Optional[int],
    remote_model: str,
) -> "RemoteProvider":
    """取得雲端 provider 實例"""
    from app.init.container import get_container
    prov = get_container().remote_service().get_provider_for_connection(conn_id, provider)
    if prov is None:
        raise RuntimeError(f"找不到可用的 {provider} 連線")
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
    純文字分 chunk 翻譯（雲端），適用於 OCR 結果、文件等無時間軸的文字。

    Returns:
        翻譯後的完整文字
    """
    from app.utils.prompts import build_translate_prompt, split_text

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
        result = prov.chat(
            model=model, messages=messages,
            max_tokens=max(len(chunk) * 4, 100), temperature=0.1,
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
    max_chars: int = LOCAL_TEXT_CHUNK_SIZE,
    glossary: Optional[dict[str, str]] = None,
    model_id: str = "translategemma",
) -> str:
    """
    純文字分 chunk 翻譯（本地 LLM），需在 runtime.acquire() context 內呼叫。

    Returns:
        翻譯後的完整文字
    """
    from app.utils.prompts import build_translate_prompt, build_translate_messages, split_text

    chunks = split_text(text, max_chars=max_chars)
    total = len(chunks)
    logger.info(f"translate_text_local: {len(text)} chars, max_chars={max_chars}, chunks={total}")
    translated_chunks = []

    for i, chunk in enumerate(chunks):
        prompt = build_translate_prompt(chunk, source_lang, target_lang, glossary=glossary, model_id=model_id)
        messages = build_translate_messages(prompt, model_id)
        result = runtime.chat(
            messages=messages,
            max_tokens=max(len(chunk) * 4, 100),
            temperature=0.1,
        )
        translated_chunks.append(result)

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
    雲端 SRT 批次翻譯

    Args:
        seg_dicts: [{"start": float, "end": float, "text": str}, ...]
        prov: RemoteProvider 實例
        model: 雲端模型 ID

    Returns:
        翻譯後的 seg_dicts 列表
    """
    from app.utils.prompts import build_srt_translate_prompt, segments_to_srt, parse_srt_response

    if batch_size is None:
        batch_size = _calc_cloud_srt_batch_size(prov, seg_dicts)

    total = len(seg_dicts)
    num_batches = (total + batch_size - 1) // batch_size
    logger.info(f"translate_srt_cloud: {total} segments, batch_size={batch_size}, batches={num_batches}")
    translated_all = []
    num_batches = (total + batch_size - 1) // batch_size

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
        translated_srt = prov.chat(
            model=model, messages=messages,
            max_tokens=len(srt_text) * 3, temperature=0.1,
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
    batch_size: int = LOCAL_BATCH_SIZE,
    keep_names: bool = True,
    style: str = "colloquial",
    glossary: Optional[dict[str, str]] = None,
    model_id: str = "translategemma",
) -> list[dict]:
    """
    本地 LLM SRT 批次翻譯（需在 runtime.acquire() context 內呼叫）

    Args:
        seg_dicts: [{"start": float, "end": float, "text": str}, ...]
        runtime: 已 acquire 的 LlamaServerRuntime 實例
        model_id: prompt 模板 ID

    Returns:
        翻譯後的 seg_dicts 列表
    """
    from app.utils.prompts import (
        build_srt_translate_prompt, build_translate_messages,
        segments_to_srt, parse_srt_response,
    )

    total = len(seg_dicts)
    num_batches = (total + batch_size - 1) // batch_size
    logger.info(f"translate_srt_local: {total} segments, batch_size={batch_size}, batches={num_batches}")
    translated_all = []
    num_batches = (total + batch_size - 1) // batch_size

    for batch_idx in range(num_batches):
        start = batch_idx * batch_size
        end = min(start + batch_size, total)
        batch = seg_dicts[start:end]

        srt_text = segments_to_srt(batch, start_index=start + 1)
        prompt = build_srt_translate_prompt(
            srt_text, source_lang, target_lang,
            keep_names=keep_names, style=style, glossary=glossary,
            model_id=model_id,
        )
        messages = build_translate_messages(prompt, model_id)
        translated_srt = runtime.chat(
            messages=messages,
            max_tokens=len(srt_text) * 3,
            temperature=0.1,
        )

        batch_translated = parse_srt_response(translated_srt, batch)
        translated_all.extend(batch_translated)

        if on_progress:
            progress = min((batch_idx + 1) / num_batches, 1.0)
            on_progress(progress, f"task.progress.translated_segment|{end}|{total}")

    return translated_all
