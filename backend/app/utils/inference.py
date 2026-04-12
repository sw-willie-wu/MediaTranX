"""
Inference parameter helper.

Provides unified access to per-model, per-task inference config.
All services should use this instead of hardcoding temperature/max_tokens.
"""
import logging
from typing import Optional

logger = logging.getLogger(__name__)


def get_inference_config(model_family: str, size: str, task: str) -> dict:
    """
    Get merged inference config for a local GGUF model.

    Merges family-level inference params with size-level capacity params.

    Returns dict with keys:
        temperature, top_k, top_p, prompt_builder,
        max_tokens_strategy, max_tokens_ratio, max_tokens_cap,
        n_ctx, n_ctx_min, n_ctx_max
    """
    from app.engine.ai.registry import MODELS_REGISTRY, FORMAT_GGUF

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
        # Max tokens strategy (from family inference)
        "max_tokens_strategy": inference.get("max_tokens_strategy", "input_ratio"),
        "max_tokens_ratio": inference.get("max_tokens_ratio", 4),
        "max_tokens_cap": inference.get("max_tokens_cap", 8192),
        # Context size (from spec)
        "n_ctx": spec.get("n_ctx_default", 4096),
        "n_ctx_min": spec.get("n_ctx_min", 2048),
        "n_ctx_max": spec.get("n_ctx_max", 8192),
        "vram_per_ctx_token": spec.get("vram_per_ctx_token", 0.04),
    }


def get_remote_inference_config(task: str, provider: str = "openai") -> dict:
    """
    Get inference config for remote providers.

    For Ollama, caller should override max_tokens after querying model ctx.
    """
    from app.engine.ai.registry import REMOTE_INFERENCE_DEFAULTS

    defaults = REMOTE_INFERENCE_DEFAULTS.get(task, {"temperature": 0.1, "max_tokens": 8192})
    return dict(defaults)


def calc_max_tokens(config: dict, n_ctx: int, input_len: int) -> int:
    """
    Calculate max_tokens based on strategy.

    Args:
        config: inference config dict (must have max_tokens_strategy, max_tokens_ratio)
        n_ctx: context window size
        input_len: estimated input token count
    """
    strategy = config.get("max_tokens_strategy", "input_ratio")

    if strategy == "input_ratio":
        raw = int(input_len * config.get("max_tokens_ratio", 4))
        capped = min(raw, config.get("max_tokens_cap", n_ctx))
    elif strategy == "context_ratio":
        capped = int(n_ctx * config.get("max_tokens_ratio", 0.5))
    else:
        capped = config.get("max_tokens_cap", 4096)

    # Safety: ensure input + output fits in context
    available = max(256, n_ctx - input_len)
    return min(capped, available)


def calc_batch_size(n_ctx: int, max_tokens: int, prompt_overhead: int,
                    avg_segment_tokens: int) -> int:
    """
    Calculate optimal batch size from available input space.

    Args:
        n_ctx: context window size
        max_tokens: reserved output tokens
        prompt_overhead: estimated tokens for prompt template
        avg_segment_tokens: average tokens per input segment
    """
    available_input = n_ctx - max_tokens - prompt_overhead
    if available_input <= 0:
        return 1
    return max(1, available_input // avg_segment_tokens)


def calc_n_ctx(spec: dict, available_vram_mb: float,
               user_override: Optional[int] = None) -> int:
    """
    Calculate optimal n_ctx from VRAM budget.

    Args:
        spec: model spec from registry (must have n_ctx_min, n_ctx_max, vram_per_ctx_token)
        available_vram_mb: available VRAM in MB after model loading
        user_override: user-set value from preferences (None = auto)
    """
    n_ctx_min = spec.get("n_ctx_min", 2048)
    n_ctx_max = spec.get("n_ctx_max", 8192)
    vram_per_token = spec.get("vram_per_ctx_token", 0.04)

    # Safe max based on VRAM
    safe_max = int(available_vram_mb / vram_per_token) if vram_per_token > 0 else n_ctx_max
    safe_max = min(safe_max, n_ctx_max)

    if user_override is not None:
        # Respect user setting but clamp to safe range
        return max(n_ctx_min, min(user_override, safe_max))

    # Auto: use default, clamped to what VRAM can afford
    default = spec.get("n_ctx_default", 4096)
    return max(n_ctx_min, min(default, safe_max))


def estimate_tokens(text: str) -> int:
    """Rough token estimate: 1 token ≈ 3.5 chars for mixed CJK/English."""
    return max(1, len(text) // 3)
