"""Tests for app.init.configs — AppSettings."""
import sys

import pytest

from app.init.configs import AppSettings, SETTINGS


class TestAppSettings:
    def test_default_platform(self, settings):
        assert settings.platform == sys.platform

    def test_default_mode(self, settings):
        assert settings.server.mode == "production"

    def test_root_path_set(self, settings):
        assert settings.path.root is not None

    def test_is_frozen_default(self, settings):
        assert settings.is_frozen is False

    def test_settings_singleton(self):
        assert isinstance(SETTINGS, AppSettings)

    def test_db_dsn_set(self, settings):
        assert "sqlite" in str(settings.db.dsn)
