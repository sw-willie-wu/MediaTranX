"""Unit tests for ModelManager new API (register_runtime, acquire, _ensure_runtime)."""
import pytest
from unittest.mock import MagicMock
from app.adapters.ai.model_manager import ModelManager, _RUNTIME_FACTORIES


class FakeRuntime:
    def __init__(self, slot="fake"):
        self.slot = slot
        self.loaded = False
        self.current_config_key = None
        self.load_calls = []
        self.unload_calls = 0

    def is_loaded(self):
        return self.loaded

    def get_current_config(self):
        return {"_key": self.current_config_key} if self.current_config_key else None

    def load(self, path, config, on_progress=None):
        self.loaded = True
        self.current_config_key = config["_key"]
        self.load_calls.append((path, config))

    def unload(self):
        self.loaded = False
        self.current_config_key = None
        self.unload_calls += 1

    def _resolve_model_path(self, model_id, variant, manager):
        return f"/fake/{model_id}/{variant}", {"model_id": model_id, "variant": variant}


def test_register_runtime_stores_instance_and_unloader():
    mm = ModelManager()
    r = FakeRuntime()
    mm.register_runtime(r)
    assert mm._runtimes["fake"] is r
    # Bound methods can't use `is` (new object each access), verify it calls unload
    mm._unloaders["fake"]()
    assert r.unload_calls == 1


def test_acquire_loads_runtime_first_time():
    mm = ModelManager()
    r = FakeRuntime()
    mm.register_runtime(r)
    with mm.acquire("fake", "family", "v1") as got:
        assert got is r
        assert r.is_loaded()
        assert r.load_calls[0][1]["_key"] == "family:v1"


def test_acquire_reuses_when_same_model():
    mm = ModelManager()
    r = FakeRuntime()
    mm.register_runtime(r)
    with mm.acquire("fake", "family", "v1"):
        pass
    with mm.acquire("fake", "family", "v1"):
        pass
    assert len(r.load_calls) == 1  # reused, not reloaded


def test_acquire_reloads_on_different_variant():
    mm = ModelManager()
    r = FakeRuntime()
    mm.register_runtime(r)
    with mm.acquire("fake", "family", "v1"):
        pass
    with mm.acquire("fake", "family", "v2"):
        pass
    assert len(r.load_calls) == 2
    assert r.unload_calls >= 1  # was unloaded before reload


def test_acquire_evicts_other_slots():
    mm = ModelManager()
    r1 = FakeRuntime(slot="slot1")
    r2 = FakeRuntime(slot="slot2")
    mm.register_runtime(r1)
    mm.register_runtime(r2)
    with mm.acquire("slot1", "m", "v"):
        pass
    with mm.acquire("slot2", "m", "v"):
        pass
    assert r1.unload_calls >= 1  # evicted when slot2 acquired


def test_acquire_unknown_slot_raises():
    mm = ModelManager()
    with pytest.raises(KeyError, match="Unknown runtime slot"):
        with mm.acquire("nope", "m", "v"):
            pass


def test_ensure_runtime_lazy_imports_from_factories(monkeypatch):
    """When slot has a factory entry, first acquire triggers lazy import."""
    mm = ModelManager()
    r = FakeRuntime(slot="whisper")

    def fake_get_whisper():
        return r

    # Patch _RUNTIME_FACTORIES to point at a fake factory
    monkeypatch.setitem(
        _RUNTIME_FACTORIES, "whisper",
        ("tests.adapters.test_model_manager_acquire", "fake_get_whisper", False),
    )
    import sys
    sys.modules["tests.adapters.test_model_manager_acquire"].fake_get_whisper = fake_get_whisper
    # First acquire creates it
    with mm.acquire("whisper", "whisper", "medium"):
        pass
    assert mm._runtimes["whisper"] is r


def test_dispatcher_slot_swap_on_model_id_change():
    """Upscale/face_restore — different model_id → unload old wrapper + load new."""
    mm = ModelManager()
    r_real = FakeRuntime(slot="upscale")
    r_bs = FakeRuntime(slot="upscale")
    r_real._dispatched_model_id = "realesrgan"

    # Simulate existing registration
    mm._runtimes["upscale"] = r_real
    mm._unloaders["upscale"] = r_real.unload

    # Fake dispatcher entry
    def fake_get_upscaler(model_id):
        if model_id == "bsrgan":
            r_bs._dispatched_model_id = "bsrgan"
            return r_bs
        return r_real

    import app.adapters.ai.model_manager as mm_mod
    mm_mod._RUNTIME_FACTORIES["upscale"] = (
        "app.adapters.ai.wrapper", "get_upscaler_TEST", True
    )
    import app.adapters.ai.wrapper
    app.adapters.ai.wrapper.get_upscaler_TEST = fake_get_upscaler
    try:
        with mm.acquire("upscale", "bsrgan", "x4"):
            pass
        assert mm._runtimes["upscale"] is r_bs
        assert r_real.unload_calls >= 1
    finally:
        del mm_mod._RUNTIME_FACTORIES["upscale"]
        del app.adapters.ai.wrapper.get_upscaler_TEST
