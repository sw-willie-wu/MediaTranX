"""MIDI editor backend service — read, save, export, and WAV conversion.

MIDI I/O helpers live in `app.utils.midi_io` (shared with the separate
service's merge path).
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional
from uuid import uuid4

from app.services.files.file_service import FileService
from app.workers.task_manager import TaskManager

logger = logging.getLogger(__name__)


class AudioMidiService:
    """MIDI read/write/export and WAV conversion service."""

    def __init__(self, file_service: FileService, task_manager: TaskManager):
        self._file_service = file_service
        self._task_manager = task_manager
        logger.info("AudioMidiService initialized")

    def read_midi(self, file_id: str) -> dict:
        """Read a .mid file and return JSON representation."""
        from app.utils.midi_io import midi_to_json

        file_info = self._file_service.require_file(file_id)
        return midi_to_json(file_info.file_path)

    def create_midi(self, data: dict) -> str:
        """Create a new .mid file from editor JSON, register it, and return file_id."""
        from app.utils.midi_io import json_to_midi

        file_id = str(uuid4())
        temp_dir = self._file_service.upload_dir
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
        from app.utils.midi_io import json_to_midi

        file_info = self._file_service.require_file(file_id)
        json_to_midi(data, file_info.file_path)
        logger.info(f"MIDI saved: {file_info.file_path}")
        return {"status": "ok", "file_id": file_id}

    async def convert_wav(
        self,
        file,
        output_format: str,
        source_file_id: Optional[str] = None,
    ) -> dict:
        """Convert uploaded audio (WAV/WebM) to target format.

        Output is written to temp/results and registered as a Results-drawer
        artefact (tool_id=audio.midi.render). Source MIDI file id is recorded
        for "來自 XX" display in the frontend.
        """
        from app.adapters.binary.ffmpeg import FFmpegWrapper

        # Create an output path in temp/results with suffix + chosen ext
        original_filename = file.filename or f"rendered.{output_format}"
        file_id, output_path = self._file_service.create_output_path(
            original_filename=original_filename,
            suffix="_rendered",
            ext=f".{output_format}",
        )
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Save uploaded blob to a sibling temp (may be WAV or WebM)
        ext = Path(file.filename or "export.webm").suffix or ".webm"
        temp_in = self._file_service.output_dir / f"_temp_in_{uuid4().hex}{ext}"
        content = await file.read()
        temp_in.write_bytes(content)

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
                input_path=temp_in,
                output_path=output_path,
                audio_codec=codec,
                audio_bitrate=bitrate,
            )
        finally:
            temp_in.unlink(missing_ok=True)

        # Register + tag as Results artefact
        self._file_service.register_output(
            file_id=file_id,
            file_path=output_path,
            original_filename=original_filename,
        )
        self._file_service.tag_as_result(
            file_id=file_id,
            tool_id="audio.midi.render",
            source_file_id=source_file_id,
        )

        return {
            "status": "ok",
            "output_file_id": file_id,
            "output_filename": output_path.name,
        }
