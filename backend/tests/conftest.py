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


@pytest.fixture
def tiny_png_path() -> Path:
    return FIXTURES_DIR / "tiny.png"


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


# ─── Wave D shared helpers ───

def make_file_service_mock(tmp_path, *, use_create_output_path: bool = True) -> MagicMock:
    """FileService mock for Wave D services.

    Set use_create_output_path=False for enhance/interpolate which bypass it and
    write directly to output_dir / output_filename.
    """
    fs = MagicMock()
    fs.output_dir = tmp_path / "out"
    fs.output_dir.mkdir(exist_ok=True)
    fs.upload_dir = tmp_path / "upload"
    fs.upload_dir.mkdir(exist_ok=True)

    if use_create_output_path:
        def _create_output_path(*, original_filename, suffix, ext=None):
            stem = Path(original_filename).stem
            resolved_ext = ext if ext is not None else Path(original_filename).suffix
            out_path = fs.output_dir / f"{stem}{suffix}{resolved_ext}"
            return f"out_{stem}{suffix}", out_path
        fs.create_output_path.side_effect = _create_output_path

    def _register_output(*, file_id, file_path, original_filename, **extra):
        return MagicMock(
            filename=Path(file_path).name,
            file_size=Path(file_path).stat().st_size if Path(file_path).exists() else 0,
        )
    fs.register_output.side_effect = _register_output

    def _require_file(file_id):
        fd = MagicMock()
        fd.file_id = file_id
        fd.original_filename = "input.png"
        fd.file_path = str(tmp_path / "input.png")
        fd.file_size = 100
        return fd
    fs.require_file.side_effect = _require_file
    return fs


# ─── Wave E shared helpers ───

def model_available(model_id: str, variant: str | None = None) -> bool:
    """Return True if the given model is downloaded.

    Used by @pytest.mark.ai integration tests to gate skipif checks. Does NOT
    require the model to be loaded — only present on disk.
    """
    try:
        from app.init.configs import SETTINGS
        base = SETTINGS.path.models / model_id
        if not base.exists():
            return False
        if variant is None:
            return any(base.iterdir())
        return any(variant in p.name for p in base.rglob("*"))
    except Exception:
        return False
