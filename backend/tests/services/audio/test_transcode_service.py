"""Unit tests for app.services.audio.transcode_service."""
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.audio.transcode_service import (
    AudioTranscodeService,
    TASK_TYPE_AUDIO_TRANSCODE,
)


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
    ffmpeg.audio_convert_sync = MagicMock()
    ffmpeg.get_media_info = AsyncMock()
    tm = MagicMock()
    svc = AudioTranscodeService(ffmpeg=ffmpeg, file_service=fs, task_manager=tm)
    return svc, fs, tm, ffmpeg


def test_init_registers_handler(tmp_path):
    svc, fs, tm, ffmpeg = _make_svc(tmp_path)
    tm.register_handler.assert_called_once()
    assert tm.register_handler.call_args.args[0] == TASK_TYPE_AUDIO_TRANSCODE


@pytest.mark.asyncio
async def test_get_audio_info_returns_media_info_dict(tmp_path):
    svc, fs, tm, ffmpeg = _make_svc(tmp_path)
    ffmpeg.get_media_info.return_value = MagicMock(
        duration=120.5, sample_rate=48000, channels=2,
        audio_codec="aac", bitrate=192000, file_size=1024,
    )
    info = await svc.get_audio_info("fid")
    assert info["duration"] == 120.5
    assert info["sample_rate"] == 48000
    assert info["codec"] == "aac"


@pytest.mark.asyncio
async def test_get_audio_info_falls_back_when_fields_missing(tmp_path):
    svc, fs, tm, ffmpeg = _make_svc(tmp_path)
    ffmpeg.get_media_info.return_value = MagicMock(
        duration=10.0, sample_rate=None, channels=None,
        audio_codec="pcm_s16le", bitrate=None, file_size=10,
    )
    info = await svc.get_audio_info("fid")
    assert info["sample_rate"] == 44100  # fallback
    assert info["channels"] == 2          # fallback


@pytest.mark.asyncio
async def test_submit_transcode_passes_params(tmp_path):
    svc, fs, tm, ffmpeg = _make_svc(tmp_path)
    async def _submit(*a, **k): return "tt"
    tm.submit.side_effect = lambda *a, **k: _submit(*a, **k)
    task_id = await svc.submit_transcode(
        file_id="fid", output_format="flac", audio_codec="flac",
        sample_rate=44100, channels=2,
    )
    assert task_id == "tt"
    args, _ = tm.submit.call_args
    p = args[1]
    assert p["output_format"] == "flac"
    assert p["audio_codec"] == "flac"
    assert p["sample_rate"] == 44100


def test_execute_lossless_flac_adds_sample_fmt_extra_args(tmp_path):
    svc, fs, tm, ffmpeg = _make_svc(tmp_path)
    svc._execute({
        "file_id": "fid", "output_format": "flac", "audio_codec": "flac",
        "audio_bitrate": "192k", "sample_rate": None, "channels": None,
    }, lambda p, m: None)
    kwargs = ffmpeg.audio_convert_sync.call_args.kwargs
    assert kwargs["audio_codec"] == "flac"
    assert kwargs["audio_bitrate"] is None  # lossless → no bitrate
    assert "-sample_fmt" in kwargs["extra_args"]
    assert "s32" in kwargs["extra_args"]


def test_execute_vorbis_maps_bitrate_to_quality(tmp_path):
    svc, fs, tm, ffmpeg = _make_svc(tmp_path)
    svc._execute({
        "file_id": "fid", "output_format": "ogg", "audio_codec": "libvorbis",
        "audio_bitrate": "192k", "sample_rate": None, "channels": None,
    }, lambda p, m: None)
    kwargs = ffmpeg.audio_convert_sync.call_args.kwargs
    assert kwargs["audio_bitrate"] is None  # vorbis uses -q:a not -b:a
    assert "-q:a" in kwargs["extra_args"]
    assert "5" in kwargs["extra_args"]


def test_execute_lossy_mp3_passes_bitrate(tmp_path):
    svc, fs, tm, ffmpeg = _make_svc(tmp_path)
    svc._execute({
        "file_id": "fid", "output_format": "mp3", "audio_codec": "libmp3lame",
        "audio_bitrate": "256k", "sample_rate": None, "channels": None,
    }, lambda p, m: None)
    kwargs = ffmpeg.audio_convert_sync.call_args.kwargs
    assert kwargs["audio_bitrate"] == "256k"
    assert kwargs["extra_args"] is None or kwargs["extra_args"] == []


def test_execute_emits_complete_progress(tmp_path):
    svc, fs, tm, ffmpeg = _make_svc(tmp_path)
    events = []
    def cb(p, m): events.append((p, m))
    svc._execute({
        "file_id": "fid", "output_format": "mp3", "audio_codec": "libmp3lame",
        "audio_bitrate": "192k", "sample_rate": None, "channels": None,
    }, cb)
    assert events[-1] == (1.0, "task.progress.transcode_complete")
    for _, m in events:
        assert m.startswith("task.progress.")
