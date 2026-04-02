"""
MIDI editor backend service — read, save, export.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable, Optional
from uuid import uuid4

from app.services.files.file_service import FileService, get_file_service
from app.workers.task_manager import TaskManager, get_task_manager

logger = logging.getLogger(__name__)

TASK_TYPE_AUDIO_MIDI_EXPORT = "audio.midi_export"


class AudioMidiService:
    _instance: Optional["AudioMidiService"] = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._file_service: FileService = get_file_service()
        self._task_manager: TaskManager = get_task_manager()
        self._task_manager.register_handler(TASK_TYPE_AUDIO_MIDI_EXPORT, self._handle_export)
        self._initialized = True
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

    async def submit_export(
        self,
        file_id: str,
        output_format: str = "wav",
        output_path: Optional[str] = None,
        output_dir: Optional[str] = None,
    ) -> str:
        """Submit MIDI export task (WAV/MP3 via FluidSynth)."""
        file_info = self._file_service.get_file(file_id)
        if file_info is None:
            raise ValueError(f"File not found: {file_id}")
        params = {
            "file_id": file_id,
            "output_format": output_format,
            "output_path": output_path,
            "output_dir": output_dir,
        }
        task_id = await self._task_manager.submit(TASK_TYPE_AUDIO_MIDI_EXPORT, params)
        logger.info(f"MIDI export task submitted: {task_id}")
        return task_id

    def _handle_export(self, params: dict, progress_callback: Callable[[float, str], None]) -> dict:
        """Handle MIDI export task — render to WAV/MP3."""
        from app.engine.fluidsynth import get_fluidsynth

        file_id = params["file_id"]
        output_format = params.get("output_format", "wav")
        custom_output_path = params.get("output_path")
        custom_output_dir = params.get("output_dir")

        file_info = self._file_service.get_file(file_id)
        if file_info is None:
            raise ValueError(f"File not found: {file_id}")

        # Determine output location: output_path (full file) > output_dir > default
        if custom_output_path:
            final_target = Path(custom_output_path)
            output_dir_path = final_target.parent
            original_stem = final_target.stem
        else:
            output_dir_path = Path(custom_output_dir) if custom_output_dir else self._file_service.output_dir
            original_stem = Path(file_info.original_filename or "midi").stem
        output_dir_path.mkdir(parents=True, exist_ok=True)

        progress_callback(0.05, "準備匯出...")

        fluidsynth = get_fluidsynth()

        # Render to WAV
        wav_filename = f"{original_stem}.wav"
        wav_path = output_dir_path / wav_filename

        fluidsynth.render_midi_to_wav(
            midi_path=str(file_info.file_path),
            output_path=str(wav_path),
            on_progress=lambda p, m: progress_callback(p * 0.8, m),
        )

        # Convert to MP3 if needed
        if output_format == "mp3":
            progress_callback(0.8, "轉換為 MP3...")
            from app.engine.ffmpeg import FFmpeg
            mp3_filename = f"{original_stem}.mp3"
            mp3_path = output_dir_path / mp3_filename
            ffmpeg = FFmpeg()
            ffmpeg.convert(str(wav_path), str(mp3_path), {"format": "mp3", "bitrate": "192k"})
            wav_path.unlink(missing_ok=True)
            final_path = mp3_path
            final_filename = mp3_filename
        elif output_format == "mid":
            # Just copy/return the original MIDI file
            progress_callback(0.9, "匯出 MIDI...")
            import shutil
            mid_filename = f"{original_stem}.mid"
            mid_path = output_dir_path / mid_filename
            if str(file_info.file_path) != str(mid_path):
                shutil.copy2(str(file_info.file_path), str(mid_path))
            final_path = mid_path
            final_filename = mid_filename
        else:
            final_path = wav_path
            final_filename = wav_filename

        # Register output
        output_file_id = str(uuid4())
        self._file_service.register_output(
            file_id=output_file_id,
            file_path=final_path,
            original_filename=file_info.original_filename,
        )

        progress_callback(1.0, "匯出完成")
        return {
            "output_file_id": output_file_id,
            "output_filename": final_filename,
        }


_service: Optional[AudioMidiService] = None


def get_audio_midi_service() -> AudioMidiService:
    global _service
    if _service is None:
        _service = AudioMidiService()
    return _service
