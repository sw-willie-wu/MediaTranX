"""Shared fixtures for MediaTranX backend tests."""
import copy
from pathlib import Path
from unittest.mock import MagicMock

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


# ─── Wave C shared fixtures + helpers ───

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def tiny_pdf_path() -> Path:
    return FIXTURES_DIR / "tiny.pdf"


@pytest.fixture
def tiny_wav_path() -> Path:
    return FIXTURES_DIR / "tiny.wav"


class _ReusableGpuSession:
    """Re-entrant `with` context — fixes single-use generator footgun seen in Wave B."""
    def __enter__(self):
        return self
    def __exit__(self, exc_type, exc, tb):
        return False


def make_model_manager_mock(llama_ready: bool = True) -> MagicMock:
    """ModelManager mock whose gpu_session() is re-entrant across multiple `with` blocks."""
    mm = MagicMock()
    mm.is_llama_ready.return_value = llama_ready
    mm.gpu_session = MagicMock(side_effect=lambda: _ReusableGpuSession())
    return mm
