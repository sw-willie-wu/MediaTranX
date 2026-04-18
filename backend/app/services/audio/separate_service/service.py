"""
Audio source separation service.
Uses Demucs to separate audio into 6 stems (vocals, drums, bass, guitar, piano, other).
"""
import logging
from pathlib import Path
from typing import Callable, Optional
from uuid import uuid4

import soundfile as sf

from app.adapters.ai.wrapper.demucs import DemucsWrapper, get_demucs
from app.adapters.ai.model_manager import ModelManager
from app.services.files.file_service import FileService
from app.workers.task_manager import TaskManager

logger = logging.getLogger(__name__)

TASK_TYPE_AUDIO_SEPARATE = "audio.separate"


class AudioSeparateService:
    """Audio source separation using Demucs (vocals, drums, bass, guitar, piano, other)."""

    def __init__(self, file_service: FileService, task_manager: TaskManager,
                 model_manager: ModelManager):
        self._demucs: DemucsWrapper = get_demucs()
        self._file_service = file_service
        self._task_manager = task_manager
        self._model_manager = model_manager
        self._task_manager.register_handler(
            TASK_TYPE_AUDIO_SEPARATE, self._handle_task,
            output_policy="results",
        )
        logger.info("AudioSeparateService initialized")

    def get_model_status(self, model_name: str = "htdemucs_6s") -> dict:
        return self._demucs.get_model_status(model_name)

    async def submit_separate(
        self,
        file_id: str,
        model_name: str = "htdemucs_6s",
        stems: Optional[list[str]] = None,
        output_format: str = "wav",
        generate_midi: bool = False,
    ) -> str:
        file_info = self._file_service.require_file(file_id)
        params = {
            "file_id": file_id,
            "model_name": model_name,
            "stems": stems,
            "output_format": output_format,
            "generate_midi": generate_midi,
        }
        task_id = await self._task_manager.submit(TASK_TYPE_AUDIO_SEPARATE, params)
        logger.info(f"Audio separate task submitted: {task_id}")
        return task_id

    def _handle_task(self, params: dict, progress_callback: Callable[[float, str], None]) -> dict:
        file_id = params["file_id"]
        file_info = self._file_service.require_file(file_id)

        model_name = params.get("model_name", "htdemucs_6s")
        stems = params.get("stems")

        original_stem = Path(file_info.original_filename).stem
        output_format = params.get("output_format", "wav")

        output_dir = self._file_service.output_dir

        midi_mode = params.get("generate_midi", False)
        demucs_progress_scale = 0.5 if midi_mode else 0.9

        progress_callback(0.0, "task.progress.loading_model_generic")

        # === GPU queue pipeline ===
        with self._model_manager.gpu_session():
            # Execute separation
            separated, sample_rate = self._demucs.separate(
                audio_path=str(file_info.file_path),
                variant=model_name,
                stems=stems,
                on_progress=lambda p, m: progress_callback(p * demucs_progress_scale, m),
            )

        write_progress_base = 0.5 if midi_mode else 0.9
        progress_callback(write_progress_base, "task.progress.writing_file")

        # Save each stem as an individual file
        output_files = []
        first_file_id = None

        for stem_name, tensor in separated.items():
            filename = f"{original_stem}.{stem_name}.{output_format}"
            file_path = output_dir / filename
            audio_data = tensor.numpy().T

            if output_format == "mp3":
                # WAV → MP3 via ffmpeg
                import tempfile
                with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                    tmp_path = tmp.name
                try:
                    sf.write(tmp_path, audio_data, sample_rate)
                    from app.adapters.binary.ffmpeg import FFmpegWrapper
                    ffmpeg = FFmpegWrapper()
                    ffmpeg.convert(tmp_path, str(file_path), {"format": "mp3", "bitrate": "192k"})
                finally:
                    Path(tmp_path).unlink(missing_ok=True)
            elif output_format == "flac":
                sf.write(str(file_path), audio_data, sample_rate, format="FLAC")
            else:
                sf.write(str(file_path), audio_data, sample_rate)

            stem_file_id = str(uuid4())
            self._file_service.register_output(
                file_id=stem_file_id, file_path=file_path, original_filename=file_info.original_filename
            )
            output_files.append({
                "file_id": stem_file_id,
                "filename": filename,
                "stem": stem_name,
                "path": str(file_path),
            })
            if first_file_id is None:
                first_file_id = stem_file_id

        result = {
            "output_file_id": first_file_id,
            "output_filename": f"{original_stem}.vocals.{output_format}",
            "output_files": output_files,
        }

        # --- MIDI conversion (optional) ---
        if midi_mode:
            progress_callback(0.6, "task.progress.converting_to_midi")

            from app.adapters.ai.wrapper.basic_pitch import get_basic_pitch
            from .midi_compose import transcribe_drums, merge_tracks_to_midi

            basic_pitch = get_basic_pitch()
            midi_tracks = []
            midi_errors = []

            # GM instrument mapping per stem
            STEM_INSTRUMENTS = {
                "vocals": 52,   # Choir Aahs
                "bass": 33,     # Electric Bass (finger)
                "guitar": 25,   # Acoustic Guitar (steel)
                "piano": 0,     # Acoustic Grand Piano
                "other": 48,    # String Ensemble 1
            }

            stem_files = {sf["stem"]: sf["path"] for sf in output_files}
            stem_names = list(stem_files.keys())

            for idx, stem_name in enumerate(stem_names):
                stem_path = stem_files[stem_name]
                stem_progress = 0.6 + (idx / len(stem_names)) * 0.3

                try:
                    if stem_name == "drums":
                        progress_callback(stem_progress, "task.progress.transcribing_drums")
                        track = transcribe_drums(stem_path)
                    else:
                        progress_callback(stem_progress, f"task.progress.converting_stem_midi|{stem_name}")
                        track = basic_pitch.audio_to_midi(stem_path)
                        track["name"] = stem_name.capitalize()
                        track["instrument"] = STEM_INSTRUMENTS.get(stem_name, 0)

                    if track["notes"]:
                        midi_tracks.append(track)
                        logger.info(f"MIDI: {stem_name} -> {len(track['notes'])} notes")
                    else:
                        logger.warning(f"MIDI: {stem_name} produced no notes, skipping")
                except Exception as e:
                    logger.warning(f"MIDI conversion failed for {stem_name}: {e}")
                    midi_errors.append(f"{stem_name}: {e}")

            if midi_tracks:
                progress_callback(0.9, "task.progress.merging_midi")
                midi_filename = f"{original_stem}.mid"
                midi_path = output_dir / midi_filename
                merge_tracks_to_midi(midi_tracks, midi_path, tempo=120.0)

                midi_file_id = str(uuid4())
                self._file_service.register_output(
                    file_id=midi_file_id,
                    file_path=midi_path,
                    original_filename=file_info.original_filename,
                )
                result["midi_file_id"] = midi_file_id
                result["midi_filename"] = midi_filename
                logger.info(f"Multi-track MIDI saved: {midi_path} ({len(midi_tracks)} tracks)")
            elif midi_errors:
                result["midi_error"] = f"MIDI conversion failed: {'; '.join(midi_errors)}"
                logger.error(f"All MIDI conversions failed: {midi_errors}")
            else:
                logger.warning("No MIDI tracks produced")

        progress_callback(1.0, "task.progress.separation_done")
        return result
