"""Image cropping service."""
import logging
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
        suppress_results: Optional[bool] = None,
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

        task_id = await self._task_manager.submit(
            TASK_TYPE_IMAGE_CROP, params, suppress_results=suppress_results
        )
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
        from app.utils.gif_utils import animation_format, apply_and_save, animation_ext

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

        progress_callback(0.7, "task.progress.saving_file")

        # Build output path
        ext = animation_ext(anim_fmt).lstrip(".") if anim_fmt else "png"
        output_file_id, output_path = self._file_service.create_output_path(
            original_filename=file_info.original_filename,
            suffix="_cropped",
            ext=f".{ext}",
        )

        with Image.open(file_info.file_path) as raw:
            apply_and_save(
                raw,
                output_path,
                lambda frame: frame.crop(box),
                on_progress=lambda p, msg: progress_callback(0.4 + p * 0.3, msg),
                preserve_alpha=True,
                static_save_kwargs={"format": "PNG"},
            )

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
