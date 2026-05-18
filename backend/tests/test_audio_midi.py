from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.audio.audio_midi_service import AudioMidiService
from app.services.files.file_service import FileService
from app.workers.task_manager import TaskManager
from app.workers.progress_tracker import ProgressTracker


class _FakeUpload:
    """Minimal duck-typed UploadFile."""
    def __init__(self, filename: str, content: bytes):
        self.filename = filename
        self._content = content

    async def read(self):
        return self._content


@pytest.mark.asyncio
async def test_convert_wav_registers_result_with_sidecar(tmp_path):
    fs = FileService(base_dir=str(tmp_path))
    tm = TaskManager(progress_tracker=ProgressTracker(), file_service=fs)
    svc = AudioMidiService(file_service=fs, task_manager=tm)

    upload = _FakeUpload("song.wav", b"\x00\x00\x00\x00")

    # Patch FFmpeg to simulate a successful conversion (write bytes to the output path)
    async def fake_audio_convert(input_path, output_path, audio_codec, audio_bitrate):
        output_path.write_bytes(b"\x00" * 256)

    with patch(
        "app.adapters.binary.ffmpeg.FFmpegWrapper.audio_convert",
        new=AsyncMock(side_effect=fake_audio_convert),
    ):
        result = await svc.convert_wav(upload, "mp3", source_file_id="midi-42")

    assert result["status"] == "ok"
    fid = result["output_file_id"]
    assert fid

    fd = fs.get_file(fid)
    assert fd is not None
    assert fd.metadata["tool_id"] == "audio.midi.render"
    assert fd.metadata["source_file_id"] == "midi-42"
    assert fd.metadata["show_in_results"] is True
    # Sidecar persisted
    assert (fs.output_dir / f"{fid}.meta.json").exists()
    # Output lives in output_dir
    assert Path(fd.file_path).is_file()


# --- read_midi / create_midi / save_midi ---

def _make_midi_svc(tmp_path):
    fs = MagicMock()
    fs.output_dir = tmp_path / "out"; fs.output_dir.mkdir()
    fs.upload_dir = tmp_path / "upload"; fs.upload_dir.mkdir()
    tm = MagicMock()
    svc = AudioMidiService(file_service=fs, task_manager=tm)
    return svc, fs, tm


def test_read_midi_delegates_to_midi_to_json(tmp_path):
    svc, fs, tm = _make_midi_svc(tmp_path)
    midi_path = tmp_path / "in.mid"
    midi_path.write_bytes(b"MThd")
    fs.require_file.return_value = MagicMock(file_path=midi_path)

    with patch("app.utils.midi_io.midi_to_json", return_value={"tracks": []}) as m:
        result = svc.read_midi("fid")
    assert result == {"tracks": []}
    m.assert_called_once_with(midi_path)


def test_create_midi_writes_file_and_registers(tmp_path):
    svc, fs, tm = _make_midi_svc(tmp_path)
    captured = []
    def _register_output(*, file_id, file_path, original_filename):
        captured.append((file_id, file_path, original_filename))
        return MagicMock(filename=Path(file_path).name, file_size=0)
    fs.register_output.side_effect = _register_output

    data = {"tempo": 120, "tracks": []}
    with patch("app.utils.midi_io.json_to_midi") as m:
        file_id = svc.create_midi(data)
    m.assert_called_once()
    args, _ = m.call_args
    assert args[0] == data
    assert len(captured) == 1
    reg_id, reg_path, reg_name = captured[0]
    assert reg_id == file_id
    assert Path(reg_path).suffix == ".mid"
    assert reg_name == "Untitled.mid"


def test_save_midi_writes_to_existing_path(tmp_path):
    svc, fs, tm = _make_midi_svc(tmp_path)
    midi_path = tmp_path / "edit.mid"
    midi_path.write_bytes(b"MThd")
    fs.require_file.return_value = MagicMock(file_path=midi_path)

    data = {"tempo": 90, "tracks": [{"notes": []}]}
    with patch("app.utils.midi_io.json_to_midi") as m:
        result = svc.save_midi("fid", data)
    assert result == {"status": "ok", "file_id": "fid"}
    args, _ = m.call_args
    assert args[0] == data
    assert args[1] == midi_path
