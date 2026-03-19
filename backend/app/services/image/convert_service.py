"""
圖片轉檔服務
"""
import asyncio
import logging
from pathlib import Path
from typing import Callable, Optional
from uuid import uuid4

from app.services.files.file_service import FileService, get_file_service
from app.workers.task_manager import TaskManager, get_task_manager

logger = logging.getLogger(__name__)

TASK_TYPE_IMAGE_CONVERT = "image.convert"


class ImageConvertService:
    """
    圖片轉檔服務
    """

    _instance: Optional["ImageConvertService"] = None

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
            TASK_TYPE_IMAGE_CONVERT,
            self._handle_convert_task
        )

        self._initialized = True
        logger.info("ImageConvertService initialized")

    async def get_image_info(self, file_id: str) -> dict:
        """取得圖片資訊"""
        from PIL import Image
        file_info = self._file_service.get_file(file_id)
        if file_info is None:
            raise ValueError(f"File not found: {file_id}")

        # 用 PIL 讀取圖片資訊
        with Image.open(file_info.file_path) as img:
            return {
                "width": img.width,
                "height": img.height,
                "format": img.format,
                "mode": img.mode,
                "file_size": file_info.file_size,
            }

    async def submit_convert(
        self,
        file_id: str,
        output_format: str = "png",
        quality: int = 85,
        width: Optional[int] = None,
        height: Optional[int] = None,
        scale: Optional[float] = None,
        output_dir: Optional[str] = None,
        output_filename: Optional[str] = None,
    ) -> str:
        """提交圖片轉檔任務"""
        file_info = self._file_service.get_file(file_id)
        if file_info is None:
            raise ValueError(f"File not found: {file_id}")

        params = {
            "file_id": file_id,
            "output_format": output_format,
            "quality": quality,
            "width": width,
            "height": height,
            "scale": scale,
            "output_dir": output_dir,
            "output_filename": output_filename,
        }

        task_id = await self._task_manager.submit(TASK_TYPE_IMAGE_CONVERT, params)
        logger.info(f"Image convert task submitted: {task_id}")

        return task_id

    def _handle_convert_task(
        self,
        params: dict,
        progress_callback: Callable[[float, str], None]
    ) -> dict:
        """處理轉檔任務（同步）"""
        return self._execute_convert(params, progress_callback)

    def _execute_convert(
        self,
        params: dict,
        progress_callback: Callable[[float, str], None]
    ) -> dict:
        """執行圖片轉檔"""
        from PIL import Image
        file_id = params["file_id"]
        file_info = self._file_service.get_file(file_id)

        if file_info is None:
            raise ValueError(f"File not found: {file_id}")

        from app.engine.gif_utils import animation_format, process_gif_frames, save_animated

        progress_callback(0.1, "載入圖片...")

        output_format = params["output_format"].upper()

        def _resize_frame(frame: Image.Image) -> Image.Image:
            if params.get("scale"):
                nw = int(frame.width * params["scale"])
                nh = int(frame.height * params["scale"])
                return frame.resize((nw, nh), Image.Resampling.LANCZOS)
            elif params.get("width") or params.get("height"):
                nw = params.get("width") or frame.width
                nh = params.get("height") or frame.height
                if params.get("width") and not params.get("height"):
                    nh = int(frame.height * (params["width"] / frame.width))
                elif params.get("height") and not params.get("width"):
                    nw = int(frame.width * (params["height"] / frame.height))
                return frame.resize((nw, nh), Image.Resampling.LANCZOS)
            return frame

        with Image.open(file_info.file_path) as raw:
            src_anim_fmt = animation_format(raw)
            # 保留動畫：輸出格式與來源動畫格式相符
            keep_anim_fmt = src_anim_fmt if (
                src_anim_fmt and (
                    (src_anim_fmt == "GIF" and output_format == "GIF") or
                    (src_anim_fmt == "PNG" and output_format == "PNG")
                )
            ) else None
            if keep_anim_fmt:
                def _convert_frame(frame, idx, total):
                    progress_callback(0.1 + idx / total * 0.5, f"轉換中 ({idx + 1}/{total})...")
                    return _resize_frame(frame)
                anim_frames = process_gif_frames(raw, _convert_frame)
            else:
                img = raw.copy()

        if not keep_anim_fmt:
            # 處理 RGBA 到 RGB 轉換（JPEG 不支援 alpha）
            if output_format in ["JPEG", "JPG"] and img.mode in ["RGBA", "P"]:
                img = img.convert("RGB")

        progress_callback(0.3, "調整尺寸...")

        if not keep_anim_fmt:
            img = _resize_frame(img)

        progress_callback(0.6, "轉換格式...")

        # 建立輸出路徑
        custom_output_dir = params.get("output_dir")
        custom_output_filename = params.get("output_filename")
        output_file_id = str(uuid4())

        # 格式對應副檔名
        ext_map = {
            "JPEG": "jpg",
            "JPG": "jpg",
            "PNG": "png",
            "WEBP": "webp",
            "GIF": "gif",
            "BMP": "bmp",
            "ICO": "ico",
            "TIFF": "tiff",
        }
        ext = ext_map.get(output_format, params["output_format"])

        if custom_output_filename:
            base_name = Path(custom_output_filename).stem
            final_filename = f"{base_name}.{ext}"
        else:
            original_stem = Path(file_info.original_filename).stem
            final_filename = f"{original_stem}_converted_{output_file_id[:8]}.{ext}"

        # 決定輸出目錄（優先自訂 > 來源目錄 > 預設 output）
        if custom_output_dir:
            output_dir_path = Path(custom_output_dir)
        elif file_info.source_dir:
            output_dir_path = Path(file_info.source_dir)
        else:
            output_dir_path = self._file_service.output_dir
        output_dir_path.mkdir(parents=True, exist_ok=True)
        output_path = output_dir_path / final_filename

        progress_callback(0.8, "儲存檔案...")

        if keep_anim_fmt:
            save_animated(anim_frames, output_path, keep_anim_fmt)
        else:
            # 儲存選項
            save_kwargs = {}
            if output_format in ["JPEG", "JPG", "WEBP"]:
                save_kwargs["quality"] = params.get("quality", 85)
            if output_format == "PNG":
                save_kwargs["optimize"] = True

            save_format = output_format
            if output_format == "JPG":
                save_format = "JPEG"

            img.save(str(output_path), format=save_format, **save_kwargs)
            img.close()

        # 註冊輸出檔案
        output_info = self._file_service.register_output(
            file_id=output_file_id,
            file_path=output_path,
            original_filename=file_info.original_filename,
        )

        progress_callback(1.0, "轉檔完成")

        return {
            "output_file_id": output_file_id,
            "output_filename": output_info.filename,
            "output_size": output_info.file_size,
        }


_image_convert_service: Optional[ImageConvertService] = None


def get_image_convert_service() -> ImageConvertService:
    global _image_convert_service
    if _image_convert_service is None:
        _image_convert_service = ImageConvertService()
    return _image_convert_service
