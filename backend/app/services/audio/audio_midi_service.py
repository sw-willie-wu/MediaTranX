"""
MIDI editor backend service — read, save, export.
"""
from __future__ import annotations

import logging
from pathlib import Path
from uuid import uuid4

from app.services.files.file_service import FileService
from app.workers.task_manager import TaskManager

logger = logging.getLogger(__name__)


class AudioMidiService:

    def __init__(self, file_service: FileService, task_manager: TaskManager):
        self._file_service = file_service
        self._task_manager = task_manager
        logger.info("AudioMidiService initialized")

    def read_midi(self, file_id: str) -> dict:
        """Read a .mid file and return JSON representation."""
        from app.utils.midi import midi_to_json

        file_info = self._file_service.get_file(file_id)
        if file_info is None:
            raise ValueError(f"File not found: {file_id}")
        return midi_to_json(file_info.file_path)

    def create_midi(self, data: dict) -> str:
        """Create a new .mid file from editor JSON, register it, and return file_id."""
        from app.utils.midi import json_to_midi
        from uuid import uuid4

        file_id = str(uuid4())
        temp_dir = self._file_service._upload_dir
        temp_dir.mkdir(parents=True, exist_ok=True)
        midi_path = temp_dir / f"{file_id}.mid"
        json_to_midi(data, str(midi_path))
        self._file_service.register_output(
            file_id=file_id,
            file_path=midi_path,
            original_filename="Untitled.mid",
        )
        logger.info(f"MIDI created: {midi_path} ({file_id})")
        return file_id

    def save_midi(self, file_id: str, data: dict) -> dict:
        """Save edited MIDI JSON back to .mid file."""
        from app.utils.midi import json_to_midi

        file_info = self._file_service.get_file(file_id)
        if file_info is None:
            raise ValueError(f"File not found: {file_id}")
        json_to_midi(data, file_info.file_path)
        logger.info(f"MIDI saved: {file_info.file_path}")
        return {"status": "ok", "file_id": file_id}

    async def convert_wav(self, file, output_format: str, output_path: str) -> dict:
        """Convert uploaded WAV file to target format using FFmpeg."""
        from app.engine.ffmpeg import FFmpegWrapper

        output_path_obj = Path(output_path)
        output_path_obj.parent.mkdir(parents=True, exist_ok=True)

        # Save uploaded audio to temp (may be WAV or WebM)
        ext = Path(file.filename or 'export.webm').suffix or '.webm'
        temp_wav = self._file_service.output_dir / f"_temp_export_{uuid4().hex}{ext}"
        temp_wav.parent.mkdir(parents=True, exist_ok=True)
        content = await file.read()
        temp_wav.write_bytes(content)

        try:
            ffmpeg = FFmpegWrapper()
            codec_map = {
                "wav": ("pcm_s16le", None),
                "mp3": ("libmp3lame", "192k"),
                "flac": ("flac", None),
                "ogg": ("libvorbis", "192k"),
                "aac": ("aac", "192k"),
            }
            codec, bitrate = codec_map.get(output_format, ("libmp3lame", "192k"))
            await ffmpeg.audio_convert(
                input_path=temp_wav,
                output_path=output_path_obj,
                audio_codec=codec,
                audio_bitrate=bitrate,
            )
        finally:
            temp_wav.unlink(missing_ok=True)

        return {"status": "ok", "output_path": str(output_path_obj)}
