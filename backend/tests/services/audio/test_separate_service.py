"""Unit tests for app.services.audio.separate_service.service."""
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from app.services.audio.separate_service.service import (
    AudioSeparateService,
    TASK_TYPE_AUDIO_SEPARATE,
)
from tests.conftest import make_model_manager_mock


def _make_svc(tmp_path):
    fs = MagicMock()
    fs.output_dir = tmp_path / "out"; fs.output_dir.mkdir()
    src = tmp_path / "song.mp3"; src.write_bytes(b"\x00")
    fi = MagicMock(file_path=src, original_filename="song.mp3")
    fs.require_file.return_value = fi

    def _register_output(*, file_id, file_path, original_filename):
        return MagicMock(filename=Path(file_path).name, file_size=0)
    fs.register_output.side_effect = _register_output

    tm = MagicMock()
    mm = make_model_manager_mock()
    demucs = MagicMock()
    # demucs.separate returns (dict of stems → tensor, sample_rate)
    # Fake tensor exposes .numpy() returning ndarray (channels, samples)
    fake_tensor = MagicMock()
    fake_tensor.numpy.return_value = np.zeros((2, 4000), dtype=np.float32)
    demucs.separate.return_value = ({"vocals": fake_tensor, "drums": fake_tensor}, 44100)
    basic_pitch = MagicMock()
    svc = AudioSeparateService(
        file_service=fs, task_manager=tm, model_manager=mm,
        demucs=demucs, basic_pitch=basic_pitch,
    )
    return svc, fs, tm, mm, demucs, basic_pitch


def test_init_registers_handler(tmp_path):
    svc, fs, tm, *_ = _make_svc(tmp_path)
    tm.register_handler.assert_called_once()
    args, kwargs = tm.register_handler.call_args
    assert args[0] == TASK_TYPE_AUDIO_SEPARATE
    assert kwargs.get("output_policy") == "results"


def test_get_model_status_delegates_to_demucs(tmp_path):
    svc, fs, tm, mm, demucs, basic_pitch = _make_svc(tmp_path)
    demucs.get_model_status.return_value = {"available": True}
    result = svc.get_model_status("htdemucs_6s")
    assert result == {"available": True}
    demucs.get_model_status.assert_called_once_with("htdemucs_6s")


@pytest.mark.asyncio
async def test_submit_separate_passes_params(tmp_path):
    svc, fs, tm, *_ = _make_svc(tmp_path)
    async def _submit(*a, **k): return "ts"
    tm.submit.side_effect = lambda *a, **k: _submit(*a, **k)
    task_id = await svc.submit_separate(
        file_id="fid", model_name="htdemucs_6s",
        stems=["vocals"], output_format="wav", generate_midi=False,
    )
    assert task_id == "ts"
    args, _ = tm.submit.call_args
    assert args[1]["stems"] == ["vocals"]
    assert args[1]["generate_midi"] is False


def test_execute_wav_format_writes_stem_files(tmp_path):
    svc, fs, tm, mm, demucs, basic_pitch = _make_svc(tmp_path)
    result = svc._execute({
        "file_id": "fid", "model_name": "htdemucs_6s", "stems": None,
        "output_format": "wav", "generate_midi": False,
    }, lambda p, m: None)
    # Expect 2 stems written (vocals, drums)
    assert len(result["output_files"]) == 2
    for f in result["output_files"]:
        assert f["filename"].endswith(".wav")
        assert (fs.output_dir / f["filename"]).exists()


def test_execute_mp3_format_calls_audio_convert_sync(tmp_path):
    """The mp3 branch does `from app.adapters.binary.ffmpeg import FFmpegWrapper`
    lazily inside the function body, then `FFmpegWrapper().audio_convert_sync(...)`.
    Patch the source module so the lazy import picks up the mock.

    After 2986c37 prod fix, the call must be audio_convert_sync with
    codec=libmp3lame + bitrate=192k (not the old broken `.convert(...)`)."""
    svc, fs, tm, mm, demucs, basic_pitch = _make_svc(tmp_path)
    with patch("app.adapters.binary.ffmpeg.FFmpegWrapper") as MockFF:
        MockFF.return_value.audio_convert_sync = MagicMock()
        svc._execute({
            "file_id": "fid", "model_name": "htdemucs_6s", "stems": None,
            "output_format": "mp3", "generate_midi": False,
        }, lambda p, m: None)
    # FFmpegWrapper instantiated once per stem (2 stems)
    assert MockFF.call_count == 2
    assert MockFF.return_value.audio_convert_sync.call_count == 2
    call = MockFF.return_value.audio_convert_sync.call_args
    assert call.kwargs["audio_codec"] == "libmp3lame"
    assert call.kwargs["audio_bitrate"] == "192k"


def test_execute_midi_mode_calls_basic_pitch_and_merge(tmp_path):
    """When generate_midi=True, non-drum stems go through basic_pitch.audio_to_midi."""
    svc, fs, tm, mm, demucs, basic_pitch = _make_svc(tmp_path)
    basic_pitch.audio_to_midi.return_value = {"notes": [{"pitch": 60, "start": 0, "duration": 0.5}]}

    with patch("app.services.audio.separate_service.midi_compose.transcribe_drums",
               return_value={"name": "Drums", "instrument": 0, "is_drum": True,
                             "notes": [{"pitch": 36, "start": 0.1, "duration": 0.1, "velocity": 100}]}), \
         patch("app.services.audio.separate_service.midi_compose.merge_tracks_to_midi") as merge:
        result = svc._execute({
            "file_id": "fid", "model_name": "htdemucs_6s", "stems": None,
            "output_format": "wav", "generate_midi": True,
        }, lambda p, m: None)

    # vocals stem (non-drum) calls basic_pitch.audio_to_midi
    assert basic_pitch.audio_to_midi.called
    merge.assert_called_once()
    assert "midi_file_id" in result


def test_execute_emits_separation_done_at_end(tmp_path):
    svc, fs, tm, *_ = _make_svc(tmp_path)
    events = []
    def cb(p, m): events.append((p, m))
    svc._execute({
        "file_id": "fid", "model_name": "htdemucs_6s", "stems": None,
        "output_format": "wav", "generate_midi": False,
    }, cb)
    assert events[-1] == (1.0, "task.progress.separation_done")
