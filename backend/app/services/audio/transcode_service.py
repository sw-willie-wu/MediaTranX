"""Audio transcoding service."""
import logging
from pathlib import Path
from typing import Callable, Optional
from uuid import uuid4

from app.engine.ffmpeg import FFmpegWrapper
from app.services.files.file_service import FileService
from app.workers.task_manager import TaskManager

logger = logging.getLogger(__name__)

TASK_TYPE_AUDIO_TRANSCODE = "audio.transcode"
DEFAULT_SAMPLE_RATE = 44100


class AudioTranscodeService:
    """Audio format conversion service with codec, bitrate, and sample rate options."""

    def __init__(self, ffmpeg: FFmpegWrapper, file_service: FileService, task_manager: TaskManager):
        self._ffmpeg = ffmpeg
        self._file_service = file_service
        self._task_manager = task_manager

        self._task_manager.register_handler(
            TASK_TYPE_AUDIO_TRANSCODE,
            self._handle_task,
            output_policy="history",
        )

        logger.info("AudioTranscodeService initialized")

    async def get_audio_info(self, file_id: str) -> dict:
        """Get audio file information."""
        file_info = self._file_service.get_file(file_id)
        if file_info is None:
            raise ValueError(f"File not found: {file_id}")

        media_info = await self._ffmpeg.get_media_info(file_info.file_path)
        return {
            "duration": media_info.duration,
            "sample_rate": DEFAULT_SAMPLE_RATE,  # TODO: get from ffprobe
            "channels": 2,
            "codec": media_info.audio_codec,
            "bitrate": media_info.bitrate,
            "file_size": media_info.file_size,
        }

    async def submit_transcode(
        self,
        file_id: str,
        output_format: str = "mp3",
        audio_codec: str = "libmp3lame",
        audio_bitrate: str = "192k",
        sample_rate: Optional[int] = None,
        channels: Optional[int] = None,
    ) -> str:
        """Submit an audio transcoding task."""
        file_info = self._file_service.get_file(file_id)
        if file_info is None:
            raise ValueError(f"File not found: {file_id}")

        params = {
            "file_id": file_id,
            "output_format": output_format,
            "audio_codec": audio_codec,
            "audio_bitrate": audio_bitrate,
            "sample_rate": sample_rate,
            "channels": channels,
        }

        task_id = await self._task_manager.submit(TASK_TYPE_AUDIO_TRANSCODE, params)
        logger.info(f"Audio transcode task submitted: {task_id}")

        return task_id

    def _handle_task(
        self,
        params: dict,
        progress_callback: Callable[[float, str], None]
    ) -> dict:
        """Handle transcoding task."""
        return self._execute(params, progress_callback)

    def _execute(
        self,
        params: dict,
        progress_callback: Callable[[float, str], None]
    ) -> dict:
        """Execute audio transcoding."""
        file_id = params["file_id"]
        file_info = self._file_service.get_file(file_id)

        if file_info is None:
            raise ValueError(f"File not found: {file_id}")

        # Build output path
        output_file_id = str(uuid4())
        original_stem = Path(file_info.original_filename).stem
        final_filename = f"{original_stem}_converted_{output_file_id[:8]}.{params['output_format']}"

        output_dir = self._file_service.output_dir
        output_path = output_dir / final_filename

        # Build extra_args (codec-specific parameters)
        codec = params["audio_codec"]
        lossless = codec in ("flac", "alac", "pcm_s16le", "pcm_s24le", "pcm_s32le")

        _VORBIS_QUALITY = {"128k": 4, "192k": 5, "256k": 7, "320k": 9}

        extra_args: list[str] = []
        bitrate = None

        if lossless:
            if codec == "flac":
                extra_args.extend(["-sample_fmt", "s32"])
        elif codec == "libvorbis":
            br = params.get("audio_bitrate", "192k")
            q = _VORBIS_QUALITY.get(br, 5)
            extra_args.extend(["-q:a", str(q)])
        elif params.get("audio_bitrate"):
            bitrate = params["audio_bitrate"]

        progress_callback(0.0, "task.progress.transcode_starting")

        self._ffmpeg.audio_convert_sync(
            input_path=file_info.file_path,
            output_path=output_path,
            audio_codec=codec,
            audio_bitrate=bitrate,
            sample_rate=params.get("sample_rate"),
            channels=params.get("channels"),
            extra_args=extra_args or None,
        )

        progress_callback(0.9, "task.progress.processing")

        output_info = self._file_service.register_output(
            file_id=output_file_id,
            file_path=output_path,
            original_filename=file_info.original_filename,
        )

        progress_callback(1.0, "task.progress.transcode_complete")

        return {
            "output_file_id": output_file_id,
            "output_filename": output_info.filename,
            "output_size": output_info.file_size,
        }
