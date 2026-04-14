"""Background removal service (rembg)."""
import logging
from pathlib import Path
from typing import Callable, Optional
from uuid import uuid4

from PIL import Image
from rembg import remove, new_session

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

    def __init__(self, file_service: FileService, task_manager: TaskManager):
        self._file_service = file_service
        self._task_manager = task_manager
        self._task_manager.register_handler(
            TASK_TYPE_IMAGE_REMOVE_BG, self._handle_task,
            output_policy="history",
        )
        logger.info("ImageRemoveBgService initialized")

    async def submit_remove_bg(
        self,
        file_id: str,
        mode: str = "auto",
    ) -> str:
        file_info = self._file_service.get_file(file_id)
        if not file_info:
            raise ValueError(f"File not found: {file_id}")
        task_id = await self._task_manager.submit(TASK_TYPE_IMAGE_REMOVE_BG, {
            "file_id": file_id,
            "mode": mode,
        })
        logger.info(f"Image remove-bg task submitted: {task_id}")
        return task_id

    def _handle_task(self, params: dict, progress_callback: Callable[[float, str], None]) -> dict:
        return self._execute(params, progress_callback)

    def _execute(self, params: dict, progress_callback: Callable[[float, str], None]) -> dict:
        file_id = params["file_id"]
        mode = params.get("mode", "auto")
        model_name = _MODE_TO_MODEL.get(mode, "u2net")

        file_info = self._file_service.get_file(file_id)

        # === GPU queue pipeline ===
        from app.init.container import get_container
        manager = get_container().model_manager()

        with manager.gpu_session():
            progress_callback(0.1, "task.progress.loading_rembg")
            # Redirect rembg model path to models/rembg/ for unified management
            import os
            from app.init.configs import SETTINGS
            rembg_dir = SETTINGS.path.models / "rembg"
            rembg_dir.mkdir(parents=True, exist_ok=True)
            os.environ["U2NET_HOME"] = str(rembg_dir)
            session = new_session(model_name)

            from app.utils.gif_utils import animation_format, process_gif_frames, save_animated, animation_ext

            with Image.open(file_info.file_path) as raw:
                anim_fmt = animation_format(raw)
                if anim_fmt:
                    def _remove_frame(frame, idx, total):
                        progress_callback(0.4 + idx / total * 0.5, f"task.progress.removing_bg|{idx + 1}|{total}")
                        return remove(frame, session=session)
                    result_frames = process_gif_frames(raw, _remove_frame)
                else:
                    img = raw.copy()

            output_file_id = str(uuid4())
            output_path = self._generate_output_path(file_info)

            progress_callback(0.9, "task.progress.saving_result")
            if anim_fmt:
                output_path = output_path.with_suffix(animation_ext(anim_fmt))
                save_animated(result_frames, output_path, anim_fmt)
            else:
                result_img = remove(img, session=session)
                result_img.save(output_path, "PNG")

        output_info = self._file_service.register_output(
            file_id=output_file_id,
            file_path=output_path,
            original_filename=file_info.original_filename,
        )
        return {
            "output_file_id": output_file_id,
            "output_filename": output_info.filename,
        }

    def _generate_output_path(self, file_info) -> Path:
        output_dir = self._file_service.output_dir
        output_dir.mkdir(parents=True, exist_ok=True)
        return output_dir / f"{Path(file_info.original_filename).stem}_nobg_{uuid4().hex[:8]}.png"
