"""Tests for OnnxWrapper (adapters/ai/wrapper/base.py).

Importing wrapper.base pulls torch at module top (transitional until Phase 7) —
acceptable in tests. onnxruntime is imported lazily inside _load_impl, so the
patch target is the REAL `onnxruntime.InferenceSession` module attribute
(mutated for the `with` scope only; mock restores it). No model file, no EP,
no GPU is touched — hermetic.
"""
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from app.adapters.ai.wrapper.base import OnnxWrapper


class _FakeSession:
    def __init__(self, providers):
        self._p = providers
        self.run = MagicMock(return_value=[np.zeros((1, 3, 4, 4), dtype=np.float32)])

    def get_providers(self):
        return self._p


def _wrapper_with(providers, *, cpu_fallback_allowed=True, gpu_ep=None):
    w = OnnxWrapper(slot="test")
    with patch("onnxruntime.InferenceSession", return_value=_FakeSession(providers)), \
         patch("app.adapters.ai.wrapper.base.select_onnx_providers",
               return_value=providers), \
         patch("app.adapters.ai.wrapper.base.is_cpu_fallback_allowed",
               return_value=cpu_fallback_allowed), \
         patch("app.adapters.ai.wrapper.base.preferred_gpu_provider",
               return_value=gpu_ep):
        w.load(model_path="x.onnx", config={"model_id": "m"})
    return w


def test_records_active_provider_and_gpu_flag():
    w = _wrapper_with(["DmlExecutionProvider", "CPUExecutionProvider"])
    assert w.active_provider == "DmlExecutionProvider"
    assert w.ran_on_gpu() is True


def test_cpu_only_session_is_not_gpu():
    w = _wrapper_with(["CPUExecutionProvider"])
    assert w.active_provider == "CPUExecutionProvider"
    assert w.ran_on_gpu() is False


def test_infer_passes_named_inputs_to_session():
    w = _wrapper_with(["CPUExecutionProvider"])
    feeds = {"input": np.zeros((1, 3, 4, 4), dtype=np.float32)}
    out = w.infer(feeds)
    assert isinstance(out[0], np.ndarray)
    w._model.run.assert_called_once_with(None, feeds)


def test_fallback_off_with_gpu_ep_but_cpu_session_raises():
    with pytest.raises(RuntimeError, match="CPU fallback is disabled"):
        _wrapper_with(["CPUExecutionProvider"], cpu_fallback_allowed=False,
                      gpu_ep="DmlExecutionProvider")


def test_fallback_off_with_gpu_session_loads():
    w = _wrapper_with(["DmlExecutionProvider", "CPUExecutionProvider"],
                      cpu_fallback_allowed=False, gpu_ep="DmlExecutionProvider")
    assert w.ran_on_gpu() is True


def test_fallback_off_on_cpu_only_host_loads():
    # No GPU EP exists at all -> CPU is not a "fallback", it is the device
    # (mirrors get_device(): policy only guards GPU-capable hosts).
    w = _wrapper_with(["CPUExecutionProvider"], cpu_fallback_allowed=False,
                      gpu_ep=None)
    assert w.active_provider == "CPUExecutionProvider"


def test_unload_drops_session_reference():
    w = _wrapper_with(["CPUExecutionProvider"])
    assert w.is_loaded()
    w.unload()
    assert not w.is_loaded()
    assert w.active_provider is None
