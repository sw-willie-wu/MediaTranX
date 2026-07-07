"""Verify BaseWrapper.acquire bridges to ModelManager.acquire."""
import pytest
from contextlib import contextmanager
from unittest.mock import MagicMock

from app.adapters.ai.wrapper.base import BaseWrapper


class _FakeWrapper(BaseWrapper):
    """Bare-bones concrete BaseWrapper for testing the bridge."""

    def _load_impl(self, model_path, config, on_progress=None):
        return MagicMock()

    def _unload_impl(self):
        pass


def test_acquire_without_manager_raises_runtimeerror():
    w = _FakeWrapper(slot="fake")
    with pytest.raises(RuntimeError, match="not registered with ModelManager"):
        with w.acquire(model_id="m", variant="v"):
            pass


def test_acquire_with_manager_delegates_to_manager():
    w = _FakeWrapper(slot="fake")

    @contextmanager
    def fake_acquire(slot, model_id, variant=None, on_progress=None, gate_class="task"):
        # Verify call shape
        assert slot == "fake"
        assert model_id == "m"
        assert variant == "v"
        assert gate_class == "task"   # 預設 gate 類別透傳
        yield w  # ModelManager.acquire yields the runtime

    mgr = MagicMock()
    mgr.acquire = fake_acquire
    w._model_manager = mgr

    with w.acquire(model_id="m", variant="v") as got:
        assert got is w


def test_acquire_passes_progress_callback():
    w = _FakeWrapper(slot="fake")
    captured = {}

    @contextmanager
    def fake_acquire(slot, model_id, variant=None, on_progress=None, gate_class="task"):
        captured["on_progress"] = on_progress
        yield w

    mgr = MagicMock()
    mgr.acquire = fake_acquire
    w._model_manager = mgr

    cb = lambda p, m: None
    with w.acquire(model_id="m", variant="v", on_progress=cb):
        pass
    assert captured["on_progress"] is cb


def test_register_runtime_attaches_manager():
    """register_runtime() must set wrapper._model_manager."""
    from app.adapters.ai.model_manager import ModelManager

    mm = ModelManager()
    w = _FakeWrapper(slot="pre-reg")
    mm.register_runtime(w)
    assert w._model_manager is mm


def test_register_runtime_provider_attaches_manager_lazily():
    """First _ensure_runtime call via provider must attach manager."""
    from app.adapters.ai.model_manager import ModelManager

    mm = ModelManager()
    w = _FakeWrapper(slot="prov-slot")
    mm.register_runtime_provider("prov-slot", lambda: w)
    # Before acquire: not attached
    assert w._model_manager is None
    # Trigger _ensure_runtime
    mm._ensure_runtime("prov-slot")
    assert w._model_manager is mm


def test_register_dispatcher_attaches_manager_per_dispatch():
    """Dispatcher path must attach manager to each newly-built wrapper."""
    from app.adapters.ai.model_manager import ModelManager

    mm = ModelManager()
    w_a = _FakeWrapper(slot="disp-slot")
    w_b = _FakeWrapper(slot="disp-slot")

    def dispatcher(model_id):
        return w_a if model_id == "a" else w_b

    mm.register_dispatcher("disp-slot", dispatcher)
    mm._ensure_runtime("disp-slot", model_id="a")
    assert w_a._model_manager is mm
    assert w_b._model_manager is None  # not built yet
    mm._ensure_runtime("disp-slot", model_id="b")
    assert w_b._model_manager is mm


def test_container_wired_wrapper_can_acquire():
    """Smoke: after init_container, a wrapper resolved from container has _model_manager set."""
    from app.init.container import init_container

    container = init_container()
    mm = container.model_manager()

    # whisper_wrapper is registered via register_runtime_provider in init_container.
    # First ensure_runtime triggers the attach.
    runtime = mm._ensure_runtime("whisper")
    assert runtime._model_manager is mm

    # And acquire() now works on the wrapper without AttributeError.
    # We don't actually acquire (would download whisper weights) — just verify the method exists.
    import inspect
    assert callable(getattr(type(runtime), "acquire", None))
    sig = inspect.signature(type(runtime).acquire)
    # Bound method on instance — verify signature has model_id, variant
    params = list(sig.parameters.keys())
    assert "model_id" in params
    assert "variant" in params
