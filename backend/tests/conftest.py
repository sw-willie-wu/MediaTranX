"""Shared fixtures for MediaTranX backend tests."""
import pytest

from app.init.configs import AppSettings, init_settings, get_settings


@pytest.fixture(autouse=True)
def _reset_settings():
    """Reset global settings before each test."""
    import app.init.configs as cfg
    cfg._settings = None
    yield
    cfg._settings = None


@pytest.fixture
def settings() -> AppSettings:
    """Provide a fresh AppSettings instance."""
    return init_settings()
