"""
圖片濾鏡服務
"""
import logging
from pathlib import Path
from typing import Callable, Optional
from uuid import uuid4

from PIL import Image, ImageEnhance

from app.services.files.file_service import FileService, get_file_service
from app.workers.task_manager import TaskManager, get_task_manager

logger = logging.getLogger(__name__)

TASK_TYPE_IMAGE_FILTER = "image.filter"


class ImageFilterService:
    """
    圖片濾鏡服務
    """

    _instance: Optional["ImageFilterService"] = None

    def __new__(cls, *args, **kwargs):
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
            TASK_TYPE_IMAGE_FILTER,
            self._handle_filter_task
        )

        self._initialized = True
        logger.info("ImageFilterService initialized")

    async def submit_filter(
        self,
        file_id: str,
        brightness: float = 1.0,
        contrast: float = 1.0,
        saturation: float = 1.0,
        sharpness: float = 1.0,
        grayscale: bool = False,
        output_dir: Optional[str] = None,
    ) -> str:
        """提交圖片濾鏡任務"""
        file_info = self._file_service.get_file(file_id)
        if file_info is None:
            raise ValueError(f"File not found: {file_id}")

        params = {
            "file_id": file_id,
            "brightness": brightness,
            "contrast": contrast,
            "saturation": saturation,
            "sharpness": sharpness,
            "grayscale": grayscale,
            "output_dir": output_dir,
        }

        task_id = await self._task_manager.submit(TASK_TYPE_IMAGE_FILTER, params)
        logger.info(f"Image filter task submitted: {task_id}")

        return task_id

    def _handle_filter_task(
        self,
        params: dict,
        progress_callback: Callable[[float, str], None]
    ) -> dict:
        """處理濾鏡任務（同步）"""
        return self._execute_filter(params, progress_callback)

    def _execute_filter(
        self,
        params: dict,
        progress_callback: Callable[[float, str], None]
    ) -> dict:
        """執行圖片濾鏡"""
        file_id = params["file_id"]
        file_info = self._file_service.get_file(file_id)

        if file_info is None:
            raise ValueError(f"File not found: {file_id}")

        progress_callback(0.1, "載入圖片...")

        img = Image.open(file_info.file_path)

        progress_callback(0.2, "套用濾鏡...")

        # 灰階處理
        if params.get("grayscale"):
            img = img.convert("L").convert("RGB")

        # 亮度
        brightness = params.get("brightness", 1.0)
        if brightness != 1.0:
            img = ImageEnhance.Brightness(img).enhance(brightness)

        # 對比度
        contrast = params.get("contrast", 1.0)
        if contrast != 1.0:
            img = ImageEnhance.Contrast(img).enhance(contrast)

        # 飽和度
        saturation = params.get("saturation", 1.0)
        if saturation != 1.0:
            img = ImageEnhance.Color(img).enhance(saturation)

        # 銳利度
        sharpness = params.get("sharpness", 1.0)
        if sharpness != 1.0:
            img = ImageEnhance.Sharpness(img).enhance(sharpness)

        progress_callback(0.7, "儲存檔案...")

        # 建立輸出路徑
        custom_output_dir = params.get("output_dir")
        output_file_id = str(uuid4())
        original_stem = Path(file_info.original_filename).stem
        final_filename = f"{original_stem}_filtered_{output_file_id[:8]}.png"

        if custom_output_dir:
            output_dir_path = Path(custom_output_dir)
        elif file_info.source_dir:
            output_dir_path = Path(file_info.source_dir)
        else:
            output_dir_path = self._file_service.output_dir
        output_dir_path.mkdir(parents=True, exist_ok=True)
        output_path = output_dir_path / final_filename

        img.save(str(output_path), format="PNG")
        img.close()

        # 註冊輸出檔案
        output_info = self._file_service.register_output(
            file_id=output_file_id,
            file_path=output_path,
            original_filename=file_info.original_filename,
        )

        progress_callback(1.0, "濾鏡套用完成")

        return {
            "output_file_id": output_file_id,
            "output_filename": output_info.filename,
        }


_image_filter_service: Optional[ImageFilterService] = None


def get_image_filter_service() -> ImageFilterService:
    global _image_filter_service
    if _image_filter_service is None:
        _image_filter_service = ImageFilterService()
    return _image_filter_service
