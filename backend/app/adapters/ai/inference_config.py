"""Inference config lookup helpers — registry-backed.

Extracted from utils/inference.py (spec §1.4: utils must not import
adapters). Thin wrappers around registry metadata for LLM inference
per-task parameters. Pure compute helpers (calc_max_tokens, etc.)
remain in utils/inference.py.
"""
from __future__ import annotations


def get_inference_config(model_family: str, size: str, task: str) -> dict:
    """
    Get merged inference config for a local GGUF model.

    Merges family-level inference params with size-level capacity params.

    Returns dict with keys:
        temperature, top_k, top_p, prompt_builder, thinking,
        max_tokens_strategy, max_tokens_ratio, max_tokens_cap,
        n_ctx, n_ctx_min, n_ctx_max, max_image_edge
    """
    from app.adapters.ai.registry import MODELS_REGISTRY, FORMAT_GGUF

    family_config = MODELS_REGISTRY.get(FORMAT_GGUF, {}).get(model_family, {})
    inference = family_config.get("inference", {}).get(task, {})
    spec = family_config.get("specs", {}).get(size, {})

    return {
        # Sampling params (from family inference)
        "temperature": inference.get("temperature", 0.1),
        "top_k": inference.get("top_k", 40),
        "top_p": inference.get("top_p", 0.9),
        "prompt_builder": inference.get("prompt_builder", "default"),
        "thinking": inference.get("thinking", False),
        "max_image_edge": inference.get("max_image_edge"),
        # Max tokens strategy (from family inference)
        "max_tokens_strategy": inference.get("max_tokens_strategy", "input_ratio"),
        "max_tokens_ratio": inference.get("max_tokens_ratio", 4),
        "max_tokens_cap": inference.get("max_tokens_cap", 8192),
        # Context size (from spec)
        "n_ctx": spec.get("n_ctx_default", 4096),
        "n_ctx_min": spec.get("n_ctx_min", 2048),
        "n_ctx_max": spec.get("n_ctx_max", 8192),
        "vram_per_ctx_token": spec.get("vram_per_ctx_token", 0.04),
        "max_srt_batch": spec.get("max_srt_batch", 0),
    }


def get_remote_inference_config(task: str) -> dict:
    """
    Get inference config for remote providers.

    For Ollama, caller should override max_tokens after querying model ctx
    (see OllamaProvider.get_model_ctx).
    """
    from app.adapters.ai.registry import REMOTE_INFERENCE_DEFAULTS

    defaults = REMOTE_INFERENCE_DEFAULTS.get(
        task, {"temperature": 0.1, "max_tokens": 8192}
    )
    return dict(defaults)
