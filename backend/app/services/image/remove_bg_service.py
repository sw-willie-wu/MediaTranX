"""Background removal service (rembg)."""
import logging
from typing import Callable

from PIL import Image
from rembg import remove, new_session

from app.adapters.ai.model_manager import ModelManager
from app.services.files.file_service import FileService
from app.workers.task_manager import TaskManager

logger = logging.getLogger(__name__)

TASK_TYPE_IMAGE_REMOVE_BG = "image.remove_bg"

_MODE_TO_MODEL = {
    "auto":    "u2net",
    "person":  "u2net_human_seg",
    "product": "isnet-general-use",
    "animal":  "u2net",
    "anime":   "isnet-anime",
}


class ImageRemoveBgService:
    """Background removal service using rembg (U2-Net / ISNet)."""

    def __init__(self, file_service: FileService, task_manager: TaskManager,
                 model_manager: ModelManager):
        self._file_service = file_service
        self._task_manager = task_manager
        self._model_manager = model_manager
        self._task_manager.register_handler(
            TASK_TYPE_IMAGE_REMOVE_BG, self._handle_task,
            output_policy="history",
        )
        logger.info("ImageRemoveBgService initialized")

    async def submit_remove_bg(
        self,
        file_id: str,
        mode: str = "auto",
        suppress_results: bool = False,
    ) -> str:
        file_info = self._file_service.require_file(file_id)
        task_id = await self._task_manager.submit(TASK_TYPE_IMAGE_REMOVE_BG, {
            "file_id": file_id,
            "mode": mode,
        }, suppress_results=suppress_results)
        logger.info(f"Image remove-bg task submitted: {task_id}")
        return task_id

    def _handle_task(self, params: dict, progress_callback: Callable[[float, str], None]) -> dict:
        return self._execute(params, progress_callback)

    def _execute(self, params: dict, progress_callback: Callable[[float, str], None]) -> dict:
        file_id = params["file_id"]
        mode = params.get("mode", "auto")
        model_name = _MODE_TO_MODEL.get(mode, "u2net")

        file_info = self._file_service.require_file(file_id)

        # === GPU queue pipeline ===
        with self._model_manager.gpu_session():
            progress_callback(0.1, "task.progress.loading_rembg")
            # Redirect rembg model path to models/rembg/ for unified management
            import os
            from app.init.configs import SETTINGS
            rembg_dir = SETTINGS.path.models / "rembg"
            rembg_dir.mkdir(parents=True, exist_ok=True)
            os.environ["U2NET_HOME"] = str(rembg_dir)
            session = new_session(model_name)

            from app.utils.gif_utils import animation_format, apply_and_save, animation_ext

            with Image.open(file_info.file_path) as raw:
                anim_fmt = animation_format(raw)

            output_file_id, output_path = self._file_service.create_output_path(
                original_filename=file_info.original_filename,
                suffix="_nobg",
                ext=".png",
            )

            if anim_fmt:
                output_path = output_path.with_suffix(animation_ext(anim_fmt))

            progress_callback(0.9, "task.progress.saving_result")

            with Image.open(file_info.file_path) as raw:
                apply_and_save(
                    raw,
                    output_path,
                    lambda frame: remove(frame, session=session),
                    on_progress=lambda p, msg: progress_callback(0.4 + p * 0.5, msg),
                    # rembg.remove() returns RGBA with its own alpha mask; preserve_alpha
                    # would overwrite that mask with the original input alpha — incorrect.
                    preserve_alpha=False,
                    static_save_kwargs={"format": "PNG"},
                )

        output_info = self._file_service.register_output(
            file_id=output_file_id,
            file_path=output_path,
            original_filename=file_info.original_filename,
        )
        return {
            "output_file_id": output_file_id,
            "output_filename": output_info.filename,
        }

