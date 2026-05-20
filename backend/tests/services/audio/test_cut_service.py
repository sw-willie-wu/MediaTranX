"""Unit tests for app.services.audio.cut_service."""
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app.services.audio.cut_service import AudioCutService, TASK_TYPE_AUDIO_CUT


def _make_svc(tmp_path):
    fs = MagicMock()
    fs.output_dir = tmp_path / "out"; fs.output_dir.mkdir()
    fs.upload_dir = tmp_path / "upload"; fs.upload_dir.mkdir()
    src = tmp_path / "in.mp3"
    src.write_bytes(b"\x00")
    fi = MagicMock(file_path=src, original_filename="in.mp3")
    fs.require_file.return_value = fi

    def _create_output_path(*, original_filename, suffix, ext):
        stem = Path(original_filename).stem
        out_path = fs.output_dir / f"{stem}{suffix}{ext}"
        return f"out_{stem}", out_path
    fs.create_output_path.side_effect = _create_output_path

    def _register_output(*, file_id, file_path, original_filename):
        return MagicMock(filename=Path(file_path).name, file_size=0)
    fs.register_output.side_effect = _register_output

    ffmpeg = MagicMock()
    ffmpeg.cut_sync = MagicMock()
    tm = MagicMock()
    svc = AudioCutService(ffmpeg=ffmpeg, file_service=fs, task_manager=tm)
    return svc, fs, tm, ffmpeg


def test_init_registers_handler(tmp_path):
    svc, fs, tm, ffmpeg = _make_svc(tmp_path)
    tm.register_handler.assert_called_once()
    args, kwargs = tm.register_handler.call_args
    assert args[0] == TASK_TYPE_AUDIO_CUT
    assert kwargs.get("output_policy") == "history"


@pytest.mark.asyncio
async def test_submit_cut_passes_params(tmp_path):
    svc, fs, tm, ffmpeg = _make_svc(tmp_path)
    async def _submit(*a, **k): return "t1"
    tm.submit.side_effect = lambda *a, **k: _submit(*a, **k)
    task_id = await svc.submit_cut(file_id="fid", start_time="00:00:01", end_time="00:00:05")
    assert task_id == "t1"
    args, _ = tm.submit.call_args
    assert args[0] == TASK_TYPE_AUDIO_CUT
    assert args[1]["start_time"] == "00:00:01"
    assert args[1]["end_time"] == "00:00:05"


def test_execute_calls_ffmpeg_cut_sync_with_stream_copy(tmp_path):
    svc, fs, tm, ffmpeg = _make_svc(tmp_path)
    events = []
    def cb(p, m): events.append((p, m))
    result = svc._execute(
        {"file_id": "fid", "start_time": "00:00:01", "end_time": "00:00:05"},
        cb,
    )
    ffmpeg.cut_sync.assert_called_once()
    kwargs = ffmpeg.cut_sync.call_args.kwargs
    assert kwargs["start_time"] == "00:00:01"
    assert kwargs["end_time"] == "00:00:05"
    assert kwargs["stream_copy"] is True
    assert "output_file_id" in result
    assert events[-1] == (1.0, "task.progress.cut_complete")
    for _, m in events:
        assert m.startswith("task.progress.")


def test_execute_preserves_original_extension(tmp_path):
    svc, fs, tm, ffmpeg = _make_svc(tmp_path)
    svc._execute({"file_id": "fid", "start_time": "0", "end_time": "1"}, lambda p, m: None)
    args, kwargs = fs.create_output_path.call_args
    assert kwargs["ext"] == ".mp3"
    assert kwargs["suffix"] == "_cut"
