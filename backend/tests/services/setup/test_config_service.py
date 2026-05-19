"""Tests for ConfigService — reads / writes .env path overrides."""
from __future__ import annotations
from pathlib import Path

import pytest

from app.services.setup.config_service import ConfigService


@pytest.fixture
def isolated_settings(tmp_path, monkeypatch):
    """Snapshot SETTINGS.path to a clean tmp dir so .env writes don't leak."""
    from app.init.configs import SETTINGS
    monkeypatch.setattr(SETTINGS.path, "root", tmp_path)
    monkeypatch.setattr(SETTINGS.path, "models", tmp_path / "models")
    monkeypatch.setattr(SETTINGS.path, "temp", tmp_path / "temp")
    return tmp_path


class TestGetConfig:
    def test_no_env_returns_empty_overrides(self, isolated_settings):
        result = ConfigService().get_config()
        assert result["models_dir"] == ""
        assert result["temp_dir"] == ""
        assert result["effective_models_dir"]  # always populated from SETTINGS
        assert result["effective_temp_dir"]

    def test_reads_user_models_dir_override(self, isolated_settings):
        (isolated_settings / ".env").write_text(
            "MEDIATRANX_PATH__MODELS=D:/custom/models\n", encoding="utf-8"
        )
        result = ConfigService().get_config()
        assert result["models_dir"] == "D:/custom/models"
        assert result["temp_dir"] == ""

    def test_reads_both_overrides(self, isolated_settings):
        (isolated_settings / ".env").write_text(
            "MEDIATRANX_PATH__MODELS=D:/mdl\nMEDIATRANX_PATH__TEMP=D:/tmp\n",
            encoding="utf-8",
        )
        result = ConfigService().get_config()
        assert result["models_dir"] == "D:/mdl"
        assert result["temp_dir"] == "D:/tmp"

    def test_ignores_unrelated_env_lines(self, isolated_settings):
        (isolated_settings / ".env").write_text(
            "SOMETHING_ELSE=foo\nMEDIATRANX_PATH__MODELS=D:/mdl\n",
            encoding="utf-8",
        )
        result = ConfigService().get_config()
        assert result["models_dir"] == "D:/mdl"


class TestUpdateConfig:
    def test_writes_new_env_when_missing(self, isolated_settings):
        result = ConfigService().update_config(models_dir="D:/new")
        assert result == {"ok": True, "restart_required": True}
        env_text = (isolated_settings / ".env").read_text(encoding="utf-8")
        assert "MEDIATRANX_PATH__MODELS=D:/new" in env_text

    def test_updates_existing_entry_in_place(self, isolated_settings):
        env = isolated_settings / ".env"
        env.write_text("MEDIATRANX_PATH__MODELS=D:/old\nKEEP_ME=yes\n", encoding="utf-8")
        ConfigService().update_config(models_dir="D:/new")
        env_text = env.read_text(encoding="utf-8")
        assert "MEDIATRANX_PATH__MODELS=D:/new" in env_text
        assert "MEDIATRANX_PATH__MODELS=D:/old" not in env_text
        assert "KEEP_ME=yes" in env_text  # untouched

    def test_no_updates_no_restart(self, isolated_settings):
        result = ConfigService().update_config()
        assert result == {"ok": True, "restart_required": False}
        assert not (isolated_settings / ".env").exists()

    def test_writes_both_paths_together(self, isolated_settings):
        ConfigService().update_config(models_dir="D:/mdl", temp_dir="D:/tmp")
        env_text = (isolated_settings / ".env").read_text(encoding="utf-8")
        assert "MEDIATRANX_PATH__MODELS=D:/mdl" in env_text
        assert "MEDIATRANX_PATH__TEMP=D:/tmp" in env_text
