"""Image cropping service."""
import logging
from pathlib import Path
from typing import Callable, Optional

from PIL import Image

from app.services.files.file_service import FileService
from app.workers.task_manager import TaskManager

logger = logging.getLogger(__name__)

TASK_TYPE_IMAGE_CROP = "image.crop"


class ImageCropService:
    """Image cropping service with animated format support."""

    def __init__(self, file_service: FileService, task_manager: TaskManager):
        self._file_service = file_service
        self._task_manager = task_manager

        self._task_manager.register_handler(
            TASK_TYPE_IMAGE_CROP,
            self._handle_task,
            output_policy="history",
        )

        logger.info("ImageCropService initialized")

    async def submit_crop(
        self,
        file_id: str,
        x: int = 0,
        y: int = 0,
        width: int = 0,
        height: int = 0,
    ) -> str:
        """Submit an image crop task."""
        file_info = self._file_service.require_file(file_id)

        params = {
            "file_id": file_id,
            "x": x,
            "y": y,
            "width": width,
            "height": height,
        }

        task_id = await self._task_manager.submit(TASK_TYPE_IMAGE_CROP, params)
        logger.info(f"Image crop task submitted: {task_id}")

        return task_id

    def _handle_task(
        self,
        params: dict,
        progress_callback: Callable[[float, str], None]
    ) -> dict:
        """Handle crop task (synchronous)."""
        return self._execute(params, progress_callback)

    def _execute(
        self,
        params: dict,
        progress_callback: Callable[[float, str], None]
    ) -> dict:
        """Execute image cropping."""
        from app.utils.gif_utils import animation_format, process_gif_frames, save_animated, animation_ext

        file_id = params["file_id"]
        file_info = self._file_service.require_file(file_id)

        progress_callback(0.1, "task.progress.loading_image")

        with Image.open(file_info.file_path) as raw:
            img_width, img_height = raw.size
            anim_fmt = animation_format(raw)

            progress_callback(0.3, "task.progress.calculating_crop")
            x = max(0, min(params["x"], img_width - 1))
            y = max(0, min(params["y"], img_height - 1))
            crop_width  = max(1, min(params["width"],  img_width  - x))
            crop_height = max(1, min(params["height"], img_height - y))
            box = (x, y, x + crop_width, y + crop_height)

            if anim_fmt:
                def _crop_frame(frame, idx, total):
                    progress_callback(0.4 + idx / total * 0.4, f"task.progress.cropping|{idx + 1}|{total}")
                    return frame.crop(box)
                result_frames = process_gif_frames(raw, _crop_frame)
            else:
                img = raw.copy().crop(box)

        progress_callback(0.7, "task.progress.saving_file")

        # Build output path
        ext = animation_ext(anim_fmt).lstrip(".") if anim_fmt else "png"
        output_file_id, output_path = self._file_service.create_output_path(
            original_filename=file_info.original_filename,
            suffix="_cropped",
            ext=f".{ext}",
        )

        if anim_fmt:
            save_animated(result_frames, output_path, anim_fmt)
        else:
            img.save(str(output_path), format="PNG")
            img.close()

        # Register output file
        output_info = self._file_service.register_output(
            file_id=output_file_id,
            file_path=output_path,
            original_filename=file_info.original_filename,
        )

        progress_callback(1.0, "task.progress.crop_complete")

        return {
            "output_file_id": output_file_id,
            "output_filename": output_info.filename,
            "crop_width": crop_width,
            "crop_height": crop_height,
            "crop_x": x,
            "crop_y": y,
            "source_width": img_width,
            "source_height": img_height,
        }
