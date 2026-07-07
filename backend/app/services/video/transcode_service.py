"""Video transcoding service."""
import logging
from dataclasses import asdict
from pathlib import Path
from typing import Any, Callable, Optional

from app.adapters.binary.ffmpeg import (
    FFmpegWrapper,
    TranscodeOptions,
    TranscodeProgress,
    VideoCodec,
    AudioCodec,
    QualityPreset,
)
from app.services.files.file_service import FileService
from app.workers.task_manager import TaskManager

logger = logging.getLogger(__name__)

# Task type constant
TASK_TYPE_VIDEO_TRANSCODE = "video.transcode"


class VideoTranscodeService:
    """Video transcoding service with codec, preset, CRF, and resolution options."""

    def __init__(self, ffmpeg: FFmpegWrapper, file_service: FileService, task_manager: TaskManager):
        self._ffmpeg = ffmpeg
        self._file_service = file_service
        self._task_manager = task_manager

        # Register task handler
        self._task_manager.register_handler(
            TASK_TYPE_VIDEO_TRANSCODE,
            self._handle_task,
            output_policy="history",
        )

        logger.info("VideoTranscodeService initialized")

    def get_ffmpeg_status(self) -> dict:
        """Query FFmpeg installation status via the injected wrapper."""
        ffmpeg = self._ffmpeg
        is_installed = ffmpeg.is_installed()
        bin_dir = str(ffmpeg.get_bin_dir())

        if is_installed:
            return {
                "installed": True,
                "ffmpeg_path": ffmpeg.ffmpeg_path,
                "ffprobe_path": ffmpeg.ffprobe_path,
                "bin_dir": bin_dir,
            }

        return {"installed": False, "ffmpeg_path": None, "ffprobe_path": None, "bin_dir": bin_dir}

    async def get_media_info(self, file_id: str) -> dict:
        """
        Get media information.

        Args:
            file_id: File ID

        Returns:
            Media information dictionary
        """
        file_info = self._file_service.require_file(file_id)

        media_info = await self._ffmpeg.get_media_info(file_info.file_path)
        return asdict(media_info)

    async def submit_transcode(
        self,
        file_id: str,
        output_format: str = "mp4",
        video_codec: str = "h264",
        audio_codec: str = "aac",
        preset: str = "medium",
        crf: int = 23,
        resolution: Optional[str] = None,
        scale_algorithm: Optional[str] = None,
        fps: Optional[float] = None,
        audio_bitrate: Optional[str] = None,
        suppress_results: bool = False,
    ) -> str:
        """
        Submit a transcoding task.

        Args:
            file_id: Input file ID
            output_format: Output format (mp4, mkv, webm, avi, mov; gif/apng for silent animations)
            video_codec: Video codec (h264, h265, vp9, av1, copy)
            audio_codec: Audio codec (aac, mp3, opus, flac, copy)
            preset: Encoding speed preset (ultrafast, fast, medium, slow, veryslow)
            crf: Quality value (0-51, lower is better)
            resolution: Resolution (e.g., "1920x1080")
            fps: Frame rate
            audio_bitrate: Audio bitrate (e.g., "128k")

        Returns:
            task_id: Task ID
        """
        # Validate file exists
        file_info = self._file_service.require_file(file_id)

        # Build task parameters
        params = {
            "file_id": file_id,
            "output_format": output_format,
            "video_codec": video_codec,
            "audio_codec": audio_codec,
            "preset": preset,
            "crf": crf,
            "resolution": resolution,
            "scale_algorithm": scale_algorithm,
            "fps": fps,
            "audio_bitrate": audio_bitrate,
        }

        # Submit task
        task_id = await self._task_manager.submit(
            TASK_TYPE_VIDEO_TRANSCODE, params, suppress_results=suppress_results
        )
        logger.info(f"Transcode task submitted: {task_id} for file {file_id}")

        return task_id

    def _handle_task(
        self,
        params: dict,
        progress_callback: Callable[[float, str], None]
    ) -> dict:
        """Handle transcoding task (runs in executor)."""
        return self._execute(params, progress_callback)

    def _execute(
        self,
        params: dict,
        progress_callback: Callable[[float, str], None]
    ) -> dict:
        """
        Execute transcoding.

        Args:
            params: Task parameters
            progress_callback: Progress callback

        Returns:
            Result dictionary
        """
        file_id = params["file_id"]
        file_info = self._file_service.require_file(file_id)

        # Map codec strings to enums
        video_codec_map = {
            "h264": VideoCodec.H264,
            "h265": VideoCodec.H265,
            "vp9": VideoCodec.VP9,
            "av1": VideoCodec.AV1,
            "copy": VideoCodec.COPY,
        }

        audio_codec_map = {
            "aac": AudioCodec.AAC,
            "mp3": AudioCodec.MP3,
            "opus": AudioCodec.OPUS,
            "flac": AudioCodec.FLAC,
            "copy": AudioCodec.COPY,
        }

        preset_map = {
            "ultrafast": QualityPreset.ULTRAFAST,
            "fast": QualityPreset.FAST,
            "medium": QualityPreset.MEDIUM,
            "slow": QualityPreset.SLOW,
            "veryslow": QualityPreset.VERYSLOW,
        }

        # Build transcode options
        options = TranscodeOptions(
            output_format=params["output_format"],
            video_codec=video_codec_map.get(params["video_codec"], VideoCodec.H264),
            audio_codec=audio_codec_map.get(params["audio_codec"], AudioCodec.AAC),
            preset=preset_map.get(params["preset"], QualityPreset.MEDIUM),
            crf=params.get("crf", 23),
            resolution=params.get("resolution"),
            scale_algorithm=params.get("scale_algorithm"),
            fps=params.get("fps"),
            audio_bitrate=params.get("audio_bitrate"),
        )

        # Build output path
        output_file_id, output_path = self._file_service.create_output_path(
            original_filename=file_info.original_filename,
            suffix="_transcoded",
            ext=f".{params['output_format']}",
        )

        # Progress callback wrapper
        def on_ffmpeg_progress(progress: TranscodeProgress):
            progress_callback(
                progress.percent / 100,
                f"task.progress.transcoding_video|{progress.percent:.1f}|{progress.speed:.1f}"
            )

        progress_callback(0.0, "task.progress.transcode_starting")

        # Execute transcode
        self._ffmpeg.transcode_sync(
            input_path=file_info.file_path,
            output_path=output_path,
            options=options,
            on_progress=on_ffmpeg_progress
        )

        # Register output file
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
