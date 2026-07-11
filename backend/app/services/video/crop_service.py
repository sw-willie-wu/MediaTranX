"""Video frame crop service."""
import logging
from pathlib import Path
from typing import Callable, Optional

from app.adapters.binary.ffmpeg import FFmpegWrapper, TranscodeProgress
from app.services.files.file_service import FileService
from app.workers.task_manager import TaskManager

logger = logging.getLogger(__name__)

TASK_TYPE_VIDEO_CROP = "video.crop"


class VideoCropService:
    """Service for cropping the visual area of a video."""

    def __init__(self, ffmpeg: FFmpegWrapper, file_service: FileService, task_manager: TaskManager):
        self._ffmpeg = ffmpeg
        self._file_service = file_service
        self._task_manager = task_manager

        self._task_manager.register_handler(
            TASK_TYPE_VIDEO_CROP,
            self._handle_task,
            output_policy="history",
        )

        logger.info("VideoCropService initialized")

    async def submit_crop(
        self,
        file_id: str,
        x: int,
        y: int,
        width: int,
        height: int,
        suppress_results: Optional[bool] = None,
    ) -> str:
        file_info = self._file_service.require_file(file_id)

        params = {
            "file_id": file_id,
            "x": x,
            "y": y,
            "width": width,
            "height": height,
        }
        task_id = await self._task_manager.submit(
            TASK_TYPE_VIDEO_CROP, params, suppress_results=suppress_results
        )
        logger.info(f"Crop task submitted: {task_id} for file {file_id}")
        return task_id

    def _handle_task(
        self,
        params: dict,
        progress_callback: Callable[[float, str], None],
    ) -> dict:
        return self._execute(params, progress_callback)

    def _execute(
        self,
        params: dict,
        progress_callback: Callable[[float, str], None],
    ) -> dict:
        file_id = params["file_id"]
        file_info = self._file_service.require_file(file_id)

        x = int(params["x"])
        y = int(params["y"])
        w = int(params["width"])
        h = int(params["height"])
        # ffmpeg crop fails on odd dimensions with yuv420p; round down to even
        w -= w % 2
        h -= h % 2
        if w <= 0 or h <= 0:
            raise ValueError(f"Invalid crop size after alignment: {w}x{h}")

        output_file_id, output_path = self._file_service.create_output_path(
            original_filename=file_info.original_filename,
            suffix="_cropped",
        )

        def on_ffmpeg_progress(progress: TranscodeProgress):
            progress_callback(
                progress.percent / 100,
                f"task.progress.cropping_video|{progress.percent:.1f}|{progress.speed:.1f}",
            )

        progress_callback(0.0, "task.progress.crop_starting")

        self._ffmpeg.crop_sync(
            input_path=file_info.file_path,
            output_path=output_path,
            x=x, y=y, width=w, height=h,
            on_progress=on_ffmpeg_progress,
        )

        output_info = self._file_service.register_output(
            file_id=output_file_id,
            file_path=output_path,
            original_filename=file_info.original_filename,
        )

        progress_callback(1.0, "task.progress.crop_complete")

        return {
            "output_file_id": output_file_id,
            "output_filename": output_info.filename,
            "crop_x": x,
            "crop_y": y,
            "crop_width": w,
            "crop_height": h,
        }
