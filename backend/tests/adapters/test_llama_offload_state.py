"""Tests for the sticky 'llama GPU offload unusable on this machine' flag."""
from __future__ import annotations

import app.adapters.ai.llama_offload_state as los


class _FakeDAO:
    """In-memory stand-in for AppSettingDAO."""
    store: dict = {}

    def get(self, key):
        return self.store.get(key)

    def set(self, key, value):
        self.store[key] = value


def _install_fake(monkeypatch, sig):
    _FakeDAO.store = {}
    monkeypatch.setattr(los, "AppSettingDAO", _FakeDAO)
    monkeypatch.setattr(los, "_current_signature", lambda: sig)


def test_unknown_when_no_row(monkeypatch):
    _install_fake(monkeypatch, {"gpu": "GTX 750 Ti", "build": "100:200"})
    assert los.llama_offload_known_broken() is False


def test_mark_then_known_broken_same_signature(monkeypatch):
    sig = {"gpu": "GTX 750 Ti", "build": "100:200"}
    _install_fake(monkeypatch, sig)
    los.mark_llama_offload_broken()
    assert los.llama_offload_known_broken() is True


def test_stale_when_gpu_changed(monkeypatch):
    _install_fake(monkeypatch, {"gpu": "GTX 750 Ti", "build": "100:200"})
    los.mark_llama_offload_broken()
    monkeypatch.setattr(los, "_current_signature",
                        lambda: {"gpu": "RTX 3080", "build": "100:200"})
    assert los.llama_offload_known_broken() is False
    assert _FakeDAO.store[los._KEY]["unusable"] is False


def test_stale_when_build_changed(monkeypatch):
    _install_fake(monkeypatch, {"gpu": "GTX 750 Ti", "build": "100:200"})
    los.mark_llama_offload_broken()
    monkeypatch.setattr(los, "_current_signature",
                        lambda: {"gpu": "GTX 750 Ti", "build": "999:999"})
    assert los.llama_offload_known_broken() is False
