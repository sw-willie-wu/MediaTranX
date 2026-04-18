import pytest
from unittest.mock import AsyncMock, patch

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
    from pathlib import Path
    assert Path(fd.file_path).is_file()
