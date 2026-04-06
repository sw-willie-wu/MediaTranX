"""Shared fixtures for MediaTranX backend tests."""
import pytest

from app.init.configs import AppSettings, SETTINGS


@pytest.fixture(autouse=True)
def _isolate_settings():
    """Snapshot and restore SETTINGS between tests to prevent mutation leaks."""
    snapshot = SETTINGS.model_dump()
    yield
    for key, value in snapshot.items():
        setattr(SETTINGS, key, value)


@pytest.fixture
def settings() -> AppSettings:
    """Provide the global AppSettings instance."""
    return SETTINGS
