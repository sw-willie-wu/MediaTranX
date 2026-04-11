"""Video transcoding service."""
import logging
from dataclasses import asdict
from pathlib import Path
from typing import Any, Callable, Optional
from uuid import uuid4

from app.engine.ffmpeg import (
    FFmpegWrapper,
    FFmpegError,
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
            self._handle_task
        )

        logger.info("VideoTranscodeService initialized")

    def get_ffmpeg_status(self) -> dict:
        """Query FFmpeg installation status."""
        is_installed = FFmpegWrapper.is_installed()
        bin_dir = str(FFmpegWrapper.get_bin_dir())

        if is_installed:
            try:
                ffmpeg = FFmpegWrapper()
                return {
                    "installed": True,
                    "ffmpeg_path": ffmpeg.ffmpeg_path,
                    "ffprobe_path": ffmpeg.ffprobe_path,
                    "bin_dir": bin_dir,
                }
            except Exception:
                pass

        return {"installed": False, "ffmpeg_path": None, "ffprobe_path": None, "bin_dir": bin_dir}

    async def get_media_info(self, file_id: str) -> dict:
        """
        Get media information.

        Args:
            file_id: File ID

        Returns:
            Media information dictionary
        """
        file_info = self._file_service.get_file(file_id)
        if file_info is None:
            raise ValueError(f"File not found: {file_id}")

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
        output_dir: Optional[str] = None,
        output_filename: Optional[str] = None,
    ) -> str:
        """
        Submit a transcoding task.

        Args:
            file_id: Input file ID
            output_format: Output format (mp4, mkv, webm, etc.)
            video_codec: Video codec (h264, h265, vp9, av1, copy)
            audio_codec: Audio codec (aac, mp3, opus, flac, copy)
            preset: Encoding speed preset (ultrafast, fast, medium, slow, veryslow)
            crf: Quality value (0-51, lower is better)
            resolution: Resolution (e.g., "1920x1080")
            fps: Frame rate
            audio_bitrate: Audio bitrate (e.g., "128k")
            output_dir: Custom output directory (optional)
            output_filename: Custom output filename (optional, without extension)

        Returns:
            task_id: Task ID
        """
        # Validate file exists
        file_info = self._file_service.get_file(file_id)
        if file_info is None:
            raise ValueError(f"File not found: {file_id}")

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
            "output_dir": output_dir,
            "output_filename": output_filename,
        }

        # Submit task
        task_id = await self._task_manager.submit(TASK_TYPE_VIDEO_TRANSCODE, params)
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
        file_info = self._file_service.get_file(file_id)

        if file_info is None:
            raise ValueError(f"File not found: {file_id}")

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
        custom_output_dir = params.get("output_dir")
        custom_output_filename = params.get("output_filename")
        output_file_id = str(uuid4())

        # Determine filename
        if custom_output_filename:
            # Use custom filename (strip user-provided extension, use selected format)
            base_name = Path(custom_output_filename).stem
            final_filename = f"{base_name}.{params['output_format']}"
        else:
            # Auto-generate filename
            original_stem = Path(file_info.original_filename).stem
            final_filename = f"{original_stem}_transcoded_{output_file_id[:8]}.{params['output_format']}"

        # Determine output directory (custom dir takes priority over default)
        output_dir = Path(custom_output_dir) if custom_output_dir else self._file_service.output_dir
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / final_filename

        # Progress callback wrapper
        def on_ffmpeg_progress(progress: TranscodeProgress):
            progress_callback(
                progress.percent / 100,
                f"Transcoding... {progress.percent:.1f}% (speed: {progress.speed:.1f}x)"
            )

        progress_callback(0.0, "task.progress.transcode_starting")

        try:
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

        except FFmpegError as e:
            logger.error(f"Transcode failed: {e}")
            raise
