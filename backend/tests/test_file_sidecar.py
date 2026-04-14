import json
from pathlib import Path

import pytest

from app.services.files.file_service import FileService


@pytest.fixture
def fs(tmp_path):
    return FileService(base_dir=str(tmp_path))


def test_write_sidecar_creates_json(fs, tmp_path):
    # Register a fake output
    output_path = fs.output_dir / "abc_test.srt"
    output_path.write_text("1\n00:00:00,000 --> 00:00:01,000\nhi\n")
    fd = fs.register_output(
        file_id="abc",
        file_path=output_path,
        original_filename="meeting.mp4",
    )
    fd.metadata = {"tool_id": "audio.transcribe", "source_file_id": "src-1", "show_in_results": True}

    fs.write_sidecar("abc")

    sidecar = fs.output_dir / "abc.meta.json"
    assert sidecar.exists()
    data = json.loads(sidecar.read_text())
    assert data["file_id"] == "abc"
    assert data["metadata"]["tool_id"] == "audio.transcribe"


def test_delete_file_removes_sidecar(fs):
    output_path = fs.output_dir / "xyz_test.srt"
    output_path.write_text("content")
    fd = fs.register_output(file_id="xyz", file_path=output_path, original_filename="x.mp4")
    fd.metadata = {"show_in_results": True}
    fs.write_sidecar("xyz")

    assert (fs.output_dir / "xyz.meta.json").exists()
    fs.delete_file("xyz")
    assert not (fs.output_dir / "xyz.meta.json").exists()
    assert not output_path.exists()


def test_scan_output_dir_loads_files_with_sidecar(fs):
    # File with sidecar
    p1 = fs.output_dir / "keep_test.srt"
    p1.write_text("x")
    fd1 = fs.register_output(file_id="keep", file_path=p1, original_filename="a.mp4")
    fd1.metadata = {"show_in_results": True, "tool_id": "audio.transcribe"}
    fs.write_sidecar("keep")

    # Orphan file without sidecar (simulates history-policy output from previous session)
    p2 = fs.output_dir / "orphan.jpg"
    p2.write_text("img")

    # Simulate restart: new FileService instance pointing at the same dirs
    fs2 = FileService(base_dir=str(fs.output_dir.parent.parent))
    fs2.scan_output_dir()

    # Only the sidecar-backed file is loaded
    assert fs2.get_file("keep") is not None
    assert fs2.get_file("keep").metadata["tool_id"] == "audio.transcribe"
    # Orphan not registered
    all_ids = list(fs2._files.keys())
    assert "keep" in all_ids
    assert all("orphan" not in fid for fid in all_ids)


def test_get_output_files_returns_only_show_in_results(fs):
    p1 = fs.output_dir / "shown_test.srt"
    p1.write_text("x")
    fd1 = fs.register_output(file_id="shown", file_path=p1, original_filename="a.mp4")
    fd1.metadata = {"show_in_results": True}

    p2 = fs.output_dir / "hidden_test.jpg"
    p2.write_text("img")
    fd2 = fs.register_output(file_id="hidden", file_path=p2, original_filename="a.jpg")
    fd2.metadata = {"show_in_results": False}

    p3 = fs.output_dir / "untagged_test.jpg"
    p3.write_text("img")
    fs.register_output(file_id="untagged", file_path=p3, original_filename="b.jpg")

    outputs = fs.get_output_files()
    ids = {f.file_id for f in outputs}
    assert ids == {"shown"}


def test_get_temp_stats_returns_sizes(fs):
    (fs.upload_dir / "a.bin").write_bytes(b"0" * 100)
    (fs.output_dir / "b.bin").write_bytes(b"0" * 250)
    stats = fs.get_temp_stats()
    assert stats["upload_bytes"] == 100
    assert stats["output_bytes"] == 250
    assert stats["total_bytes"] == 350
