"""register_local_file guards: directories must be rejected (folder-ingest hardening)."""
import pytest

from app.handler.exceptions import FileNotFoundError_
from app.services.files.file_service import FileService


def test_register_local_file_rejects_directory(tmp_path):
    svc = FileService()
    with pytest.raises(FileNotFoundError_):
        svc.register_local_file(str(tmp_path))  # 目錄不是檔案


def test_register_local_file_ok(tmp_path):
    p = tmp_path / "a.png"
    p.write_bytes(b"x")
    svc = FileService()
    fd = svc.register_local_file(str(p))
    assert fd.file_size == 1
    assert fd.original_filename == "a.png"
