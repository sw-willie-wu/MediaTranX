"""Tests for the files API list/stats endpoints (Task 1.6)."""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.init.container import AppContainer
from app.services.files.file_service import FileService


@pytest.fixture
def client(tmp_path):
    """Create a FastAPI app with a temp-backed FileService wired in."""
    container = AppContainer()
    temp_fs = FileService(base_dir=str(tmp_path))
    container.file_service.override(temp_fs)

    from app.api.routes.files import router as files_router

    app = FastAPI()
    app.include_router(files_router, prefix="/api/files")
    container.wire(packages=["app.api.routes.files"])

    try:
        yield TestClient(app), temp_fs
    finally:
        container.unwire()
        container.file_service.reset_override()


def test_list_output_filter(client):
    tc, fs = client
    p1 = fs.output_dir / "a.srt"
    p1.write_text("x")
    fd1 = fs.register_output(file_id="a", file_path=p1, original_filename="in.mp4")
    fd1.metadata = {"show_in_results": True, "tool_id": "audio.transcribe"}

    p2 = fs.output_dir / "b.jpg"
    p2.write_text("x")
    fs.register_output(file_id="b", file_path=p2, original_filename="in.jpg")

    res = tc.get("/api/files?kind=output")
    assert res.status_code == 200
    data = res.json()
    assert len(data) == 1
    assert data[0]["file_id"] == "a"
    assert data[0]["metadata"]["show_in_results"] is True


def test_stats_returns_sizes(client):
    tc, fs = client
    (fs.upload_dir / "a.bin").write_bytes(b"0" * 100)
    (fs.output_dir / "b.bin").write_bytes(b"0" * 50)

    res = tc.get("/api/files/stats")
    assert res.status_code == 200
    data = res.json()
    assert data["upload_bytes"] == 100
    assert data["output_bytes"] == 50
    assert data["total_bytes"] == 150
