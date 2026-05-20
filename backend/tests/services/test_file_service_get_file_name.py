"""Unit tests for FileService.get_file_name."""
import pytest

from app.services.files.file_service import FileService


@pytest.fixture
def file_service(tmp_path, monkeypatch):
    monkeypatch.setenv("MEDIATRANX_PATH__ROOT", str(tmp_path))
    return FileService(base_dir=str(tmp_path))


def test_get_file_name_resolves_original_filename(file_service, tmp_path):
    p = tmp_path / "x.mp4"
    p.write_text("x", encoding="utf-8")
    file_service.register_output(file_id="fid-1", file_path=p,
                                 original_filename="my video.mp4")
    assert file_service.get_file_name("fid-1") == "my video.mp4"


def test_get_file_name_none_or_empty_file_id_returns_none(file_service):
    assert file_service.get_file_name(None) is None
    assert file_service.get_file_name("") is None


def test_get_file_name_unregistered_returns_none(file_service):
    assert file_service.get_file_name("not-registered") is None
