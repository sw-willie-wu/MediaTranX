"""
去背服務（rembg）
"""
import logging
from pathlib import Path
from typing import Callable, Optional
from uuid import uuid4
from PIL import Image

from backend.services.files.file_service import FileService, get_file_service
from backend.workers.task_manager import TaskManager, get_task_manager

logger = logging.getLogger(__name__)

TASK_TYPE_IMAGE_REMOVE_BG = "image.remove_bg"

_MODE_TO_MODEL = {
    "auto":    "u2net",
    "person":  "u2net_human_seg",
    "product": "isnet-general-use",
    "animal":  "u2net",
}


class ImageRemoveBgService:
    _instance: Optional["ImageRemoveBgService"] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._file_service: FileService = get_file_service()
        self._task_manager: TaskManager = get_task_manager()
        self._task_manager.register_handler(TASK_TYPE_IMAGE_REMOVE_BG, self._handle_remove_bg_task)
        self._initialized = True
        logger.info("ImageRemoveBgService initialized")

    async def submit_remove_bg(
        self,
        file_id: str,
        mode: str = "auto",
        output_dir: Optional[str] = None,
    ) -> str:
        file_info = self._file_service.get_file(file_id)
        if not file_info:
            raise ValueError(f"File not found: {file_id}")
        task_id = await self._task_manager.submit(TASK_TYPE_IMAGE_REMOVE_BG, {
            "file_id": file_id,
            "mode": mode,
            "output_dir": output_dir,
        })
        return task_id

    def _handle_remove_bg_task(self, params: dict, progress_callback: Callable) -> dict:
        from rembg import remove, new_session

        file_id = params["file_id"]
        mode = params.get("mode", "auto")
        model_name = _MODE_TO_MODEL.get(mode, "u2net")

        file_info = self._file_service.get_file(file_id)

        progress_callback(0.1, "載入去背模型...")
        session = new_session(model_name)

        progress_callback(0.4, "去除背景中...")
        with Image.open(file_info.file_path) as img:
            img = img.copy()

        result_img = remove(img, session=session)

        output_file_id = str(uuid4())
        output_path = self._generate_output_path(file_info, params.get("output_dir"))

        progress_callback(0.9, "儲存結果...")
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

    def _generate_output_path(self, file_info, custom_dir) -> Path:
        target_dir = Path(custom_dir) if custom_dir else self._file_service.output_dir
        target_dir.mkdir(parents=True, exist_ok=True)
        return target_dir / f"{Path(file_info.original_filename).stem}_nobg_{uuid4().hex[:8]}.png"


def get_image_remove_bg_service() -> ImageRemoveBgService:
    return ImageRemoveBgService()
