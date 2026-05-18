"""Contract tests for app.adapters.ai.inference_config.

Drift guard: if `MODELS_REGISTRY` or `REMOTE_INFERENCE_DEFAULTS` schema changes
(e.g. a family loses an `inference[task]` entry, or a key is renamed/dropped),
these tests fail loudly. Unit-level service tests mock `_FAKE_CONFIG` and
can't catch registry drift on their own.

No GPU, no model load — pure dict-shape inspection.
"""
from __future__ import annotations

import pytest

from app.adapters.ai.inference_config import (
    get_inference_config,
    get_remote_inference_config,
)
from app.adapters.ai.registry import (
    FORMAT_GGUF,
    MODELS_REGISTRY,
    REMOTE_INFERENCE_DEFAULTS,
)


_REQUIRED_LOCAL_KEYS = {
    "temperature", "top_k", "top_p", "prompt_builder", "thinking",
    "max_tokens_strategy", "max_tokens_ratio", "max_tokens_cap",
    "n_ctx", "n_ctx_min", "n_ctx_max",
    "vram_per_ctx_token", "max_srt_batch",
}

_VALID_MAX_TOKENS_STRATEGIES = {"input_ratio", "context_ratio", "fixed"}


def _family_task_size_combinations():
    """Yield (family, task, size) for every entry actually defined in MODELS_REGISTRY."""
    gguf = MODELS_REGISTRY.get(FORMAT_GGUF, {})
    for family_name, family_config in gguf.items():
        tasks = family_config.get("inference", {})
        sizes = family_config.get("specs", {})
        if not tasks or not sizes:
            continue
        first_size = next(iter(sizes.keys()))
        for task_name in tasks.keys():
            yield family_name, task_name, first_size


@pytest.mark.parametrize("family,task,size", list(_family_task_size_combinations()))
def test_local_inference_config_shape(family: str, task: str, size: str):
    """Every registered (family, task, size) must resolve to a dict with all required keys."""
    cfg = get_inference_config(family, size, task)
    missing = _REQUIRED_LOCAL_KEYS - set(cfg.keys())
    assert not missing, f"({family},{task},{size}) missing keys: {missing}"

    # Spot-check types
    assert isinstance(cfg["temperature"], (int, float))
    assert isinstance(cfg["top_k"], int)
    assert isinstance(cfg["top_p"], (int, float))
    assert isinstance(cfg["prompt_builder"], str) and cfg["prompt_builder"]
    assert isinstance(cfg["thinking"], bool)
    assert cfg["max_tokens_strategy"] in _VALID_MAX_TOKENS_STRATEGIES, \
        f"({family},{task}) bad max_tokens_strategy={cfg['max_tokens_strategy']!r}"
    assert isinstance(cfg["max_tokens_cap"], int) and cfg["max_tokens_cap"] > 0
    assert isinstance(cfg["n_ctx"], int) and cfg["n_ctx"] > 0
    assert cfg["n_ctx_min"] <= cfg["n_ctx"] <= cfg["n_ctx_max"]


def test_local_inference_config_unknown_family_uses_defaults():
    """Unknown family must not raise — falls back to safe defaults."""
    cfg = get_inference_config("nonexistent_family_xyz", "4b", "translate")
    # Required keys still present (defaults)
    assert _REQUIRED_LOCAL_KEYS - set(cfg.keys()) == set()
    assert cfg["temperature"] == 0.1
    assert cfg["max_tokens_strategy"] == "input_ratio"


@pytest.mark.parametrize("task", list(REMOTE_INFERENCE_DEFAULTS.keys()))
def test_remote_inference_config_shape(task: str):
    """Every task in REMOTE_INFERENCE_DEFAULTS must resolve to a dict with required keys."""
    cfg = get_remote_inference_config(task)
    assert "temperature" in cfg
    assert "max_tokens" in cfg
    assert isinstance(cfg["temperature"], (int, float))
    assert isinstance(cfg["max_tokens"], int) and cfg["max_tokens"] > 0


def test_remote_inference_config_unknown_task_uses_fallback():
    """Unknown task must not raise — returns safe default."""
    cfg = get_remote_inference_config("nonexistent_task_xyz")
    assert cfg == {"temperature": 0.1, "max_tokens": 8192}


def test_remote_inference_config_returns_copy_not_reference():
    """Mutating the returned dict must not mutate REMOTE_INFERENCE_DEFAULTS."""
    cfg = get_remote_inference_config("translate")
    original_max = REMOTE_INFERENCE_DEFAULTS["translate"]["max_tokens"]
    cfg["max_tokens"] = -999
    assert REMOTE_INFERENCE_DEFAULTS["translate"]["max_tokens"] == original_max


def test_known_vlm_families_support_ocr_and_frame_select():
    """Regression guard: families used by image_ocr / doc_ocr / video summary must keep their task entries."""
    # Wave A consumers depend on these:
    vlm_families = ["qwen3vl", "internvl2.5", "gemma4", "qwen3.5"]
    gguf = MODELS_REGISTRY.get(FORMAT_GGUF, {})
    for family in vlm_families:
        assert family in gguf, f"VLM family {family} disappeared from registry"
        inference = gguf[family].get("inference", {})
        assert "ocr" in inference, f"{family} lost 'ocr' inference config"
        assert "frame_select" in inference, f"{family} lost 'frame_select' inference config"


def test_known_text_families_support_translate_and_summarize():
    """Regression guard: text-LLM families used by translate/summary services."""
    text_families = ["qwen3", "qwen3.5", "gemma3", "gemma4", "internvl2.5"]
    gguf = MODELS_REGISTRY.get(FORMAT_GGUF, {})
    for family in text_families:
        assert family in gguf, f"text family {family} disappeared from registry"
        inference = gguf[family].get("inference", {})
        assert "translate" in inference, f"{family} lost 'translate' inference config"
        assert "summarize" in inference, f"{family} lost 'summarize' inference config"
