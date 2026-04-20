"""Unit tests for ModelManager new API (register_runtime, acquire, _ensure_runtime)."""
import pytest
from app.adapters.ai.model_manager import ModelManager


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


def test_runtime_provider_invoked_on_first_acquire():
    """Non-dispatcher slot with registered provider: first acquire calls provider."""
    mm = ModelManager()
    r = FakeRuntime(slot="whisper")
    call_count = {"n": 0}

    def provider():
        call_count["n"] += 1
        return r

    mm.register_runtime_provider("whisper", provider)
    # First acquire resolves via provider
    with mm.acquire("whisper", "whisper", "medium"):
        pass
    assert mm._runtimes["whisper"] is r
    assert call_count["n"] == 1
    # Second acquire reuses cached runtime (provider not called again)
    with mm.acquire("whisper", "whisper", "medium"):
        pass
    assert call_count["n"] == 1


def test_dispatcher_swaps_runtime_on_model_id_change():
    """Dispatcher slot: different model_id → unload old wrapper + load new."""
    mm = ModelManager()
    r_real = FakeRuntime(slot="upscale")
    r_bs = FakeRuntime(slot="upscale")

    def dispatcher(model_id):
        if model_id == "bsrgan":
            return r_bs
        return r_real

    mm.register_dispatcher("upscale", dispatcher)

    with mm.acquire("upscale", "realesrgan", "x4"):
        pass
    assert mm._runtimes["upscale"] is r_real

    with mm.acquire("upscale", "bsrgan", "x4"):
        pass
    assert mm._runtimes["upscale"] is r_bs
    assert r_real.unload_calls >= 1
