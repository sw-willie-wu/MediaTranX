"""
圖片裁切服務
"""
import logging
from pathlib import Path
from typing import Callable, Optional
from uuid import uuid4

from app.services.files.file_service import FileService, get_file_service
from app.workers.task_manager import TaskManager, get_task_manager

logger = logging.getLogger(__name__)

TASK_TYPE_IMAGE_CROP = "image.crop"


class ImageCropService:
    """
    圖片裁切服務
    """

    _instance: Optional["ImageCropService"] = None

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
            TASK_TYPE_IMAGE_CROP,
            self._handle_crop_task
        )

        self._initialized = True
        logger.info("ImageCropService initialized")

    async def submit_crop(
        self,
        file_id: str,
        x: int = 0,
        y: int = 0,
        width: int = 0,
        height: int = 0,
        output_dir: Optional[str] = None,
    ) -> str:
        """提交圖片裁切任務"""
        file_info = self._file_service.get_file(file_id)
        if file_info is None:
            raise ValueError(f"File not found: {file_id}")

        params = {
            "file_id": file_id,
            "x": x,
            "y": y,
            "width": width,
            "height": height,
            "output_dir": output_dir,
        }

        task_id = await self._task_manager.submit(TASK_TYPE_IMAGE_CROP, params)
        logger.info(f"Image crop task submitted: {task_id}")

        return task_id

    def _handle_crop_task(
        self,
        params: dict,
        progress_callback: Callable[[float, str], None]
    ) -> dict:
        """處理裁切任務（同步）"""
        return self._execute_crop(params, progress_callback)

    def _execute_crop(
        self,
        params: dict,
        progress_callback: Callable[[float, str], None]
    ) -> dict:
        """執行圖片裁切"""
        from PIL import Image
        from app.engine.gif_utils import animation_format, process_gif_frames, save_animated, animation_ext

        file_id = params["file_id"]
        file_info = self._file_service.get_file(file_id)

        if file_info is None:
            raise ValueError(f"File not found: {file_id}")

        progress_callback(0.1, "載入圖片...")

        with Image.open(file_info.file_path) as raw:
            img_width, img_height = raw.size
            anim_fmt = animation_format(raw)

            progress_callback(0.3, "計算裁切範圍...")
            x = max(0, min(params["x"], img_width - 1))
            y = max(0, min(params["y"], img_height - 1))
            crop_width  = max(1, min(params["width"],  img_width  - x))
            crop_height = max(1, min(params["height"], img_height - y))
            box = (x, y, x + crop_width, y + crop_height)

            if anim_fmt:
                def _crop_frame(frame, idx, total):
                    progress_callback(0.4 + idx / total * 0.4, f"裁切中 ({idx + 1}/{total})...")
                    return frame.crop(box)
                result_frames = process_gif_frames(raw, _crop_frame)
            else:
                img = raw.copy().crop(box)

        progress_callback(0.7, "儲存檔案...")

        # 建立輸出路徑
        custom_output_dir = params.get("output_dir")
        output_file_id = str(uuid4())
        original_stem = Path(file_info.original_filename).stem
        ext = animation_ext(anim_fmt).lstrip(".") if anim_fmt else "png"
        final_filename = f"{original_stem}_cropped_{output_file_id[:8]}.{ext}"

        if custom_output_dir:
            output_dir_path = Path(custom_output_dir)
        elif file_info.source_dir:
            output_dir_path = Path(file_info.source_dir)
        else:
            output_dir_path = self._file_service.output_dir
        output_dir_path.mkdir(parents=True, exist_ok=True)
        output_path = output_dir_path / final_filename

        if anim_fmt:
            save_animated(result_frames, output_path, anim_fmt)
        else:
            img.save(str(output_path), format="PNG")
            img.close()

        # 註冊輸出檔案
        output_info = self._file_service.register_output(
            file_id=output_file_id,
            file_path=output_path,
            original_filename=file_info.original_filename,
        )

        progress_callback(1.0, "裁切完成")

        return {
            "output_file_id": output_file_id,
            "output_filename": output_info.filename,
            "width": crop_width,
            "height": crop_height,
        }


_image_crop_service: Optional[ImageCropService] = None


def get_image_crop_service() -> ImageCropService:
    global _image_crop_service
    if _image_crop_service is None:
        _image_crop_service = ImageCropService()
    return _image_crop_service
