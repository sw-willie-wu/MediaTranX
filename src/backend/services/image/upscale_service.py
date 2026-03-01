"""
圖片超解析與增強服務 (REFACTOR V4.1)
"""
import logging
from pathlib import Path
from typing import Callable, Optional
from uuid import uuid4
from PIL import Image

from backend.services.files.file_service import FileService, get_file_service
from backend.workers.task_manager import TaskManager, get_task_manager
logger = logging.getLogger(__name__)

TASK_TYPE_IMAGE_UPSCALE = "image.upscale"


class ImageUpscaleService:
    _instance: Optional["ImageUpscaleService"] = None

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

        self._task_manager.register_handler(
            TASK_TYPE_IMAGE_UPSCALE,
            self._handle_upscale_task,
        )

        self._initialized = True
        logger.info("ImageUpscaleService initialized")

    async def submit_upscale(
        self,
        file_id: str,
        model_id: str = "realesrgan-x4plus",
        scale: int = 4,
        sharpen: bool = False,
        face_fix: bool = False,
        output_dir: Optional[str] = None,
    ) -> str:
        file_info = self._file_service.get_file(file_id)
        if not file_info:
            raise ValueError(f"File not found: {file_id}")

        task_id = await self._task_manager.submit(TASK_TYPE_IMAGE_UPSCALE, {
            "file_id": file_id,
            "model_id": model_id,
            "scale": scale,
            "sharpen": sharpen,
            "face_fix": face_fix,
            "output_dir": output_dir,
        })
        return task_id

    def _handle_upscale_task(self, params: dict, progress_callback: Callable) -> dict:
        file_id  = params["file_id"]
        model_id = params["model_id"]
        scale    = params["scale"]

        file_info = self._file_service.get_file(file_id)

        progress_callback(0.1, f"正在載入模型: {model_id}...")

        from backend.core.ai.upscale import get_realesrgan
        with Image.open(file_info.file_path) as img:
            result_img = get_realesrgan().enhance(
                img,
                model_id=model_id,
                scale=scale,
                on_progress=lambda p, m: progress_callback(0.1 + p * 0.2, m),
            )

        output_file_id = str(uuid4())
        output_path = self._generate_output_path(file_info, scale, params.get("output_dir"))
        result_img.save(output_path, "PNG")

        progress_callback(0.95, "正在註冊結果...")
        output_info = self._file_service.register_output(
            file_id=output_file_id,
            file_path=output_path,
            original_filename=file_info.original_filename,
        )

        return {
            "output_file_id": output_file_id,
            "output_filename": output_info.filename,
            "scale": scale,
        }

    def _generate_output_path(self, file_info, scale, custom_dir) -> Path:
        target_dir = Path(custom_dir) if custom_dir else self._file_service.output_dir
        target_dir.mkdir(parents=True, exist_ok=True)
        return target_dir / f"{Path(file_info.original_filename).stem}_x{scale}_{uuid4().hex[:8]}.png"


def get_image_upscale_service() -> ImageUpscaleService:
    return ImageUpscaleService()
