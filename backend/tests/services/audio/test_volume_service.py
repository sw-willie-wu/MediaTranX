"""Unit tests for app.services.audio.volume_service."""
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app.services.audio.volume_service import AudioVolumeService, TASK_TYPE_AUDIO_VOLUME


def _make_svc(tmp_path):
    fs = MagicMock()
    fs.output_dir = tmp_path / "out"; fs.output_dir.mkdir()
    src = tmp_path / "in.wav"; src.write_bytes(b"\x00")
    fi = MagicMock(file_path=src, original_filename="in.wav")
    fs.require_file.return_value = fi

    def _create_output_path(*, original_filename, suffix, ext):
        stem = Path(original_filename).stem
        return f"out_{stem}", fs.output_dir / f"{stem}{suffix}{ext}"
    fs.create_output_path.side_effect = _create_output_path

    def _register_output(*, file_id, file_path, original_filename):
        return MagicMock(filename=Path(file_path).name, file_size=0)
    fs.register_output.side_effect = _register_output

    ffmpeg = MagicMock()
    ffmpeg.adjust_volume_sync = MagicMock()
    tm = MagicMock()
    svc = AudioVolumeService(ffmpeg=ffmpeg, file_service=fs, task_manager=tm)
    return svc, fs, tm, ffmpeg


def test_init_registers_handler(tmp_path):
    svc, fs, tm, ffmpeg = _make_svc(tmp_path)
    tm.register_handler.assert_called_once()
    assert tm.register_handler.call_args.args[0] == TASK_TYPE_AUDIO_VOLUME


@pytest.mark.asyncio
async def test_submit_volume_passes_params(tmp_path):
    svc, fs, tm, ffmpeg = _make_svc(tmp_path)
    async def _submit(*a, **k): return "tv"
    tm.submit.side_effect = lambda *a, **k: _submit(*a, **k)
    task_id = await svc.submit_volume(file_id="fid", volume_db=-3.0, normalize=False)
    assert task_id == "tv"
    args, _ = tm.submit.call_args
    assert args[1]["volume_db"] == -3.0
    assert args[1]["normalize"] is False


def test_execute_normalize_uses_loudnorm_filter(tmp_path):
    svc, fs, tm, ffmpeg = _make_svc(tmp_path)
    svc._execute({"file_id": "fid", "volume_db": 0.0, "normalize": True}, lambda p, m: None)
    assert ffmpeg.adjust_volume_sync.call_args.kwargs["af_filter"] == "loudnorm"


def test_execute_volume_db_uses_volume_filter(tmp_path):
    svc, fs, tm, ffmpeg = _make_svc(tmp_path)
    svc._execute({"file_id": "fid", "volume_db": 6.0, "normalize": False}, lambda p, m: None)
    assert ffmpeg.adjust_volume_sync.call_args.kwargs["af_filter"] == "volume=+6.0dB"


def test_execute_emits_complete_progress(tmp_path):
    svc, fs, tm, ffmpeg = _make_svc(tmp_path)
    events = []
    def cb(p, m): events.append((p, m))
    svc._execute({"file_id": "fid", "volume_db": 0.0, "normalize": True}, cb)
    assert events[-1] == (1.0, "task.progress.volume_complete")
    for _, m in events:
        assert m.startswith("task.progress.")


def test_execute_normalized_suffix_in_filename(tmp_path):
    svc, fs, tm, ffmpeg = _make_svc(tmp_path)
    svc._execute({"file_id": "fid", "volume_db": 0.0, "normalize": True}, lambda p, m: None)
    suffix = fs.create_output_path.call_args.kwargs["suffix"]
    assert suffix == "_normalized"


def test_execute_volume_suffix_includes_db(tmp_path):
    svc, fs, tm, ffmpeg = _make_svc(tmp_path)
    svc._execute({"file_id": "fid", "volume_db": -3.0, "normalize": False}, lambda p, m: None)
    suffix = fs.create_output_path.call_args.kwargs["suffix"]
    assert "vol-3dB" in suffix
