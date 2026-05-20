"""Unit tests for FileService.read_text."""
import pytest
from pathlib import Path
from app.services.files.file_service import FileService


@pytest.fixture
def file_service(tmp_path, monkeypatch):
    monkeypatch.setenv("MEDIATRANX_PATH__ROOT", str(tmp_path))
    return FileService(base_dir=str(tmp_path))


def test_read_text_returns_content(file_service, tmp_path):
    p = tmp_path / "sample.txt"
    p.write_text("hello world", encoding="utf-8")
    file_service.register_output(file_id="fid-1", file_path=p, original_filename="sample.txt")
    assert file_service.read_text("fid-1") == "hello world"


def test_read_text_missing_file_id_returns_none(file_service):
    assert file_service.read_text("not-registered") is None


def test_read_text_path_missing_returns_none(file_service, tmp_path):
    p = tmp_path / "gone.txt"
    p.write_text("x", encoding="utf-8")
    file_service.register_output(file_id="fid-2", file_path=p, original_filename="gone.txt")
    p.unlink()
    assert file_service.read_text("fid-2") is None


def test_read_text_invalid_utf8_returns_none(file_service, tmp_path):
    p = tmp_path / "bad.bin"
    p.write_bytes(b"\xff\xfe\x00\x80\x81\x82")
    file_service.register_output(file_id="fid-3", file_path=p, original_filename="bad.bin")
    assert file_service.read_text("fid-3") is None
