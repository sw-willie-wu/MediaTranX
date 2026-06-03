"""R2 regression: _resolve_gguf_path must inject required_vram_mb into config.

Separate from tests/adapters/test_llm_wrapper.py (chat/stream behaviour) to
avoid a duplicate basename. Covers the _resolve_gguf_path VRAM injection only.

Note: the _load_impl ngl gating that used to live here has moved into
compute_policy.resolve_device_for_task (covered by test_compute_policy.py's
test_resolve_cuda_vram_insufficient_downgrades_and_notifies) and the
device→ngl mapping is covered by
tests/adapters/ai/wrapper/test_llm_gpu_fallback.py.
"""
from __future__ import annotations
from unittest.mock import patch, MagicMock

from app.adapters.ai.wrapper.llm import LlmWrapper


def test_resolve_gguf_injects_required_vram_mb():
    w = LlmWrapper(slot="llm")
    manager = MagicMock()
    manager.get_model_path.return_value = "some/path.gguf"
    manager.get_vram_requirement.return_value = 2130
    with patch("app.adapters.ai.registry.MODELS_REGISTRY", {
        "GGUF": {"qwen3": {
            "default_variant": {"1.7b": "Q8_0"},
            "specs": {"1.7b": {
                "layers": 29, "n_ctx_default": 4096,
                "variants": {"Q8_0": {"file": "model.gguf"}},
            }},
        }}
    }):
        _, config = w._resolve_gguf_path("qwen3", "1.7b", manager)
    assert config["required_vram_mb"] == 2130
    manager.get_vram_requirement.assert_called_once_with("qwen3", "1.7b:Q8_0")
