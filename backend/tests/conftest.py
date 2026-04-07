"""Shared fixtures for MediaTranX backend tests."""
import copy
import pytest

from app.init.configs import AppSettings, SETTINGS


@pytest.fixture(autouse=True)
def _isolate_settings():
    """Snapshot and restore SETTINGS between tests to prevent mutation leaks."""
    snapshot = copy.deepcopy(dict(
        server=SETTINGS.server,
        path=SETTINGS.path,
        db=SETTINGS.db,
        is_frozen=SETTINGS.is_frozen,
        platform=SETTINGS.platform,
    ))
    yield
    for key, value in snapshot.items():
        setattr(SETTINGS, key, value)


@pytest.fixture
def settings() -> AppSettings:
    """Provide the global AppSettings instance."""
    return SETTINGS
