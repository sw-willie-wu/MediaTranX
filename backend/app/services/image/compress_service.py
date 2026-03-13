"""
圖片壓縮服務
"""
import logging
from pathlib import Path
from typing import Callable, Optional
from uuid import uuid4

from PIL import Image

from app.services.files.file_service import FileService, get_file_service
from app.workers.task_manager import TaskManager, get_task_manager

logger = logging.getLogger(__name__)

TASK_TYPE_IMAGE_COMPRESS = "image.compress"


class ImageCompressService:
    """
    圖片壓縮服務
    """

    _instance: Optional["ImageCompressService"] = None

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
            TASK_TYPE_IMAGE_COMPRESS,
            self._handle_compress_task
        )

        self._initialized = True
        logger.info("ImageCompressService initialized")

    async def submit_compress(
        self,
        file_id: str,
        output_format: str = "jpeg",
        quality: int = 80,
        output_dir: Optional[str] = None,
    ) -> str:
        """提交圖片壓縮任務"""
        file_info = self._file_service.get_file(file_id)
        if file_info is None:
            raise ValueError(f"File not found: {file_id}")

        params = {
            "file_id": file_id,
            "output_format": output_format,
            "quality": quality,
            "output_dir": output_dir,
        }

        task_id = await self._task_manager.submit(TASK_TYPE_IMAGE_COMPRESS, params)
        logger.info(f"Image compress task submitted: {task_id}")

        return task_id

    def _handle_compress_task(
        self,
        params: dict,
        progress_callback: Callable[[float, str], None]
    ) -> dict:
        """處理壓縮任務（同步）"""
        return self._execute_compress(params, progress_callback)

    def _execute_compress(
        self,
        params: dict,
        progress_callback: Callable[[float, str], None]
    ) -> dict:
        """執行圖片壓縮"""
        file_id = params["file_id"]
        file_info = self._file_service.get_file(file_id)

        if file_info is None:
            raise ValueError(f"File not found: {file_id}")

        progress_callback(0.1, "載入圖片...")

        # 記錄輸入檔案大小
        input_size = file_info.file_size

        img = Image.open(file_info.file_path)

        progress_callback(0.3, "處理圖片模式...")

        output_format = params["output_format"].lower()
        save_format = output_format.upper()

        # JPEG 不支援 alpha channel
        if output_format in ["jpeg", "jpg"] and img.mode in ["RGBA", "P"]:
            img = img.convert("RGB")
            save_format = "JPEG"

        # 副檔名對應
        ext_map = {
            "jpeg": "jpg",
            "jpg": "jpg",
            "webp": "webp",
            "png": "png",
        }
        ext = ext_map.get(output_format, output_format)

        progress_callback(0.6, "壓縮並儲存檔案...")

        # 建立輸出路徑
        custom_output_dir = params.get("output_dir")
        output_file_id = str(uuid4())
        original_stem = Path(file_info.original_filename).stem
        final_filename = f"{original_stem}_compressed_{output_file_id[:8]}.{ext}"

        if custom_output_dir:
            output_dir_path = Path(custom_output_dir)
        elif file_info.source_dir:
            output_dir_path = Path(file_info.source_dir)
        else:
            output_dir_path = self._file_service.output_dir
        output_dir_path.mkdir(parents=True, exist_ok=True)
        output_path = output_dir_path / final_filename

        # 儲存選項
        save_kwargs = {"quality": params.get("quality", 80)}
        if output_format == "png":
            save_kwargs = {"optimize": True}

        img.save(str(output_path), format=save_format, **save_kwargs)
        img.close()

        # 計算壓縮率
        output_size = output_path.stat().st_size
        if input_size > 0:
            size_reduction_percent = round((1 - output_size / input_size) * 100)
        else:
            size_reduction_percent = 0

        # 註冊輸出檔案
        output_info = self._file_service.register_output(
            file_id=output_file_id,
            file_path=output_path,
            original_filename=file_info.original_filename,
        )

        progress_callback(1.0, "壓縮完成")

        return {
            "output_file_id": output_file_id,
            "output_filename": output_info.filename,
            "output_size": output_size,
            "size_reduction_percent": size_reduction_percent,
        }


_image_compress_service: Optional[ImageCompressService] = None


def get_image_compress_service() -> ImageCompressService:
    global _image_compress_service
    if _image_compress_service is None:
        _image_compress_service = ImageCompressService()
    return _image_compress_service
