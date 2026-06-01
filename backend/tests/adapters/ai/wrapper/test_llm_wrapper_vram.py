"""R2 regression: llama-server n_gpu_layers must be VRAM-aware.

Separate from tests/adapters/test_llm_wrapper.py (chat/stream behaviour) to
avoid a duplicate basename. Covers the _resolve_gguf_path VRAM injection and
the _load_impl ngl gating that prevent OOM on small-VRAM GPUs (e.g. 2GB 750 Ti).
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


def _load_with(config_extra, nvidia, fits):
    w = LlmWrapper(slot="llm")
    captured = {}
    fake_server = MagicMock()

    def _start(**kw):
        captured.update(kw)

    fake_server.start.side_effect = _start
    base = {"layers": 29, "n_ctx": 4096}
    base.update(config_extra)
    with patch("app.adapters.ai.wrapper.llm.LlamaServer", return_value=fake_server), \
         patch("app.adapters.device.has_nvidia_gpu", return_value=nvidia), \
         patch("app.adapters.device.fits_in_vram", return_value=fits):
        w._load_impl("p.gguf", base)
    return captured["n_gpu_layers"]


def test_ngl_zero_when_nvidia_but_vram_insufficient():
    assert _load_with({"required_vram_mb": 5000}, nvidia=True, fits=False) == 0


def test_ngl_full_when_vram_fits():
    assert _load_with({"required_vram_mb": 2130}, nvidia=True, fits=True) == 29


def test_ngl_zero_when_no_nvidia():
    assert _load_with({"required_vram_mb": 2130}, nvidia=False, fits=True) == 0


def test_ngl_full_when_required_unknown():
    # required_vram_mb missing/0 → don't downgrade (preserve legacy behaviour)
    assert _load_with({}, nvidia=True, fits=False) == 29
