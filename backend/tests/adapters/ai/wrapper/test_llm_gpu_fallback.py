"""_load_impl: proactive compat gate + reactive CPU fallback on hard crash."""
from __future__ import annotations

from pathlib import Path

import pytest

import app.adapters.ai.wrapper.llm as llm_mod
from app.adapters.ai.wrapper.llm import LlmWrapper
from app.adapters.binary.llama_server import LlamaServerCrashError


class _FakeServer:
    """Records start() calls; optionally hard-crashes on the first GPU start."""
    def __init__(self, crash_on_gpu=False):
        self.crash_on_gpu = crash_on_gpu
        self.calls = []  # n_gpu_layers per start()

    # keep signature in sync with LlamaServer.start
    def start(self, *, model_path, n_ctx, n_gpu_layers, mmproj_path, on_progress):
        self.calls.append(n_gpu_layers)
        if self.crash_on_gpu and n_gpu_layers > 0:
            raise LlamaServerCrashError(code=3221225477,
                                        reason="ACCESS_VIOLATION (0xC0000005)",
                                        is_hard_crash=True)

    def stop(self):
        self.calls.append("stop")  # records the clean-up between crash and CPU retry


def _make_wrapper():
    return LlmWrapper(slot="llm")


def _patch_env(monkeypatch, *, device_choice, fallback_allowed=True,
               sticky_broken=False, server=None):
    # _load_impl does `from app.adapters.compute_policy import resolve_device_for_task`
    # (and the others) lazily inside the function, so patching the SOURCE module
    # attribute is what takes effect at call time.
    import app.adapters.compute_policy as cp
    import app.adapters.device as dev
    import app.adapters.ai.llama_offload_state as los
    monkeypatch.setattr(cp, "resolve_device_for_task",
                        lambda vram, model_id=None: device_choice)
    monkeypatch.setattr(dev, "is_cpu_fallback_allowed", lambda: fallback_allowed)
    monkeypatch.setattr(los, "llama_offload_known_broken", lambda: sticky_broken)
    marked = {"v": False}
    monkeypatch.setattr(los, "mark_llama_offload_broken",
                        lambda: marked.__setitem__("v", True))
    notices = []
    import app.utils.task_notices as tn
    monkeypatch.setattr(tn, "push_task_notice",
                        lambda code, **kw: notices.append((code, kw)))
    monkeypatch.setattr(llm_mod, "LlamaServer", lambda: server)
    return marked, notices


CONFIG = {"model_id": "qwen3", "layers": 99, "n_ctx": 4096, "required_vram_mb": 2000}


def test_proactive_cpu_when_device_not_cuda(monkeypatch):
    srv = _FakeServer()
    _patch_env(monkeypatch, device_choice="cpu", server=srv)
    w = _make_wrapper()
    w._load_impl(Path("m.gguf"), CONFIG, None)
    assert srv.calls == [0]


def test_proactive_cpu_when_sticky_broken(monkeypatch):
    srv = _FakeServer()
    _patch_env(monkeypatch, device_choice="cuda", sticky_broken=True, server=srv)
    w = _make_wrapper()
    w._load_impl(Path("m.gguf"), CONFIG, None)
    assert srv.calls == [0]


def test_gpu_used_when_compatible(monkeypatch):
    srv = _FakeServer()
    _patch_env(monkeypatch, device_choice="cuda", server=srv)
    w = _make_wrapper()
    w._load_impl(Path("m.gguf"), CONFIG, None)
    assert srv.calls == [99]


def test_reactive_retry_cpu_on_hard_crash_when_fallback_on(monkeypatch):
    srv = _FakeServer(crash_on_gpu=True)
    marked, notices = _patch_env(monkeypatch, device_choice="cuda", server=srv)
    w = _make_wrapper()
    w._load_impl(Path("m.gguf"), CONFIG, None)
    # crashed on GPU(99) → stop() cleaned the dead process → retried on CPU(0)
    assert srv.calls == [99, "stop", 0]
    assert marked["v"] is True
    assert ("gpu_unsupported", {"model": "qwen3"}) in notices


def test_reactive_off_propagates_without_retry(monkeypatch):
    srv = _FakeServer(crash_on_gpu=True)
    marked, notices = _patch_env(monkeypatch, device_choice="cuda",
                                 fallback_allowed=False, server=srv)
    w = _make_wrapper()
    with pytest.raises(LlamaServerCrashError):
        w._load_impl(Path("m.gguf"), CONFIG, None)
    assert srv.calls == [99]
    assert marked["v"] is False
