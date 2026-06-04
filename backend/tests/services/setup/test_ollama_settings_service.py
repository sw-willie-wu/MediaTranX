from unittest.mock import patch

import pytest

from app.services.setup.ollama_settings_service import (
    OllamaSettingsService,
    _env_default,
)


# ── _env_default (env fallback, clamped) ──

def test_env_default_unset_is_8192(monkeypatch):
    monkeypatch.delenv("MTX_OLLAMA_MAX_NUM_CTX", raising=False)
    assert _env_default() == 8192


def test_env_default_valid_passthrough(monkeypatch):
    monkeypatch.setenv("MTX_OLLAMA_MAX_NUM_CTX", "32768")
    assert _env_default() == 32768


def test_env_default_below_min_clamps_to_4096(monkeypatch):
    monkeypatch.setenv("MTX_OLLAMA_MAX_NUM_CTX", "100")
    assert _env_default() == 4096


def test_env_default_above_max_clamps_to_131072(monkeypatch):
    monkeypatch.setenv("MTX_OLLAMA_MAX_NUM_CTX", "200000")
    assert _env_default() == 131072


def test_env_default_non_integer_is_8192(monkeypatch):
    monkeypatch.setenv("MTX_OLLAMA_MAX_NUM_CTX", "not-a-number")
    assert _env_default() == 8192


# ── get_settings ──

def test_get_settings_db_empty_uses_env(monkeypatch):
    monkeypatch.setenv("MTX_OLLAMA_MAX_NUM_CTX", "16384")
    svc = OllamaSettingsService()
    with patch.object(svc._dao, "get", return_value=None):
        assert svc.get_settings().ollama_num_ctx_cap == 16384


def test_get_settings_db_value_wins(monkeypatch):
    monkeypatch.setenv("MTX_OLLAMA_MAX_NUM_CTX", "16384")
    svc = OllamaSettingsService()
    with patch.object(svc._dao, "get", return_value={"ollama_num_ctx_cap": 65536}):
        assert svc.get_settings().ollama_num_ctx_cap == 65536


def test_get_settings_row_missing_key_uses_env(monkeypatch):
    monkeypatch.delenv("MTX_OLLAMA_MAX_NUM_CTX", raising=False)
    svc = OllamaSettingsService()
    with patch.object(svc._dao, "get", return_value={"unrelated": 1}):
        assert svc.get_settings().ollama_num_ctx_cap == 8192


# ── update_settings ──

def test_update_persists_and_pushes_cap():
    svc = OllamaSettingsService()
    with patch.object(svc._dao, "get", return_value={"ollama_num_ctx_cap": 8192}), \
         patch.object(svc._dao, "set") as mock_set, \
         patch("app.adapters.ai.remote.ollama.set_num_ctx_cap") as mock_apply:
        out = svc.update_settings({"ollama_num_ctx_cap": 32768})
    assert out.ollama_num_ctx_cap == 32768
    mock_set.assert_called_once_with("ollama", {"ollama_num_ctx_cap": 32768})
    mock_apply.assert_called_once_with(32768)


# ── apply_persisted ──

def test_apply_persisted_pushes_current_value():
    svc = OllamaSettingsService()
    with patch.object(svc._dao, "get", return_value={"ollama_num_ctx_cap": 12288}), \
         patch("app.adapters.ai.remote.ollama.set_num_ctx_cap") as mock_apply:
        svc.apply_persisted()
    mock_apply.assert_called_once_with(12288)
