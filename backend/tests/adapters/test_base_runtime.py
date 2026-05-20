"""Unit tests for BaseWrapper new public API (no container ref)."""
import pytest
from unittest.mock import MagicMock
from app.adapters.ai.wrapper.base import BaseWrapper


class FakeRuntime(BaseWrapper):
    def __init__(self):
        super().__init__(slot="fake")
        self.load_calls = []
        self.unload_calls = 0

    def _load_impl(self, model_path, config, on_progress=None):
        self.load_calls.append((model_path, config))
        return {"loaded": model_path}

    def _unload_impl(self):
        self.unload_calls += 1


def test_init_no_container_reference():
    r = FakeRuntime()
    assert r.slot == "fake"
    # Accessing a container attr should fail — runtime must not hold one
    assert not hasattr(r, "_manager")


def test_load_sets_model_and_config():
    r = FakeRuntime()
    r.load("/path/to/model", {"_key": "a:1"})
    assert r.is_loaded()
    assert r.get_current_config() == {"_key": "a:1"}


def test_unload_clears_model_and_config():
    r = FakeRuntime()
    r.load("/path", {"_key": "x"})
    r.unload()
    assert not r.is_loaded()
    assert r.get_current_config() is None


def test_load_twice_replaces_and_calls_unload_impl():
    r = FakeRuntime()
    r.load("/a", {"_key": "a"})
    r.load("/b", {"_key": "b"})
    assert r.unload_calls == 1
    assert r.get_current_config() == {"_key": "b"}


def test_resolve_model_path_default_uses_injected_manager():
    r = FakeRuntime()
    mgr = MagicMock()
    mgr.get_model_path.return_value = "/p"
    mgr.get_model_config.return_value = {"layers": 32}
    path, config = r._resolve_model_path("family", "var", mgr)
    assert path == "/p"
    assert config["layers"] == 32
    assert config["model_id"] == "family"
    assert config["variant"] == "var"
