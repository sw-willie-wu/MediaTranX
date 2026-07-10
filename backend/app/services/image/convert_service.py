"""Image format conversion service."""
import logging
from pathlib import Path
from typing import Callable, Optional

from PIL import Image

from app.adapters.binary.gifsicle import GifsicleWrapper
from app.services.files.file_service import FileService
from app.workers.task_manager import TaskManager

logger = logging.getLogger(__name__)

TASK_TYPE_IMAGE_CONVERT = "image.convert"


class ImageConvertService:
    """Image format conversion with resize and quality options."""

    # info 路徑的 palette 抽樣預算。注意：Pillow 逐幀 decode 是預算無關的下限
    # （17 幀 2560×2240 實測 ~0.8s），抽樣只省 set(getdata()) 數色成本 →
    # 全掃 6.2s → 約 1.0s（~6×）。palette 已背景化（?palette=1），不在切換
    # 關鍵路徑。compress 路徑不用此常數（保持精確全掃）。
    _PALETTE_SAMPLE_BUDGET = 2_000_000

    def __init__(self, file_service: FileService, task_manager: TaskManager,
                 gifsicle: GifsicleWrapper | None = None):
        self._file_service = file_service
        self._task_manager = task_manager
        self._gifsicle = gifsicle

        self._task_manager.register_handler(
            TASK_TYPE_IMAGE_CONVERT,
            self._handle_task,
            output_policy="history",
        )

        logger.info("ImageConvertService initialized")

    async def get_image_info(self, file_id: str, include_palette: bool = False) -> dict:
        """Get image information. palette_size only when include_palette (approx, fast)."""
        from app.utils.gif_utils import is_animated
        from app.utils.gif_colors import count_gif_colors

        file_info = self._file_service.require_file(file_id)

        # Read image info with PIL
        with Image.open(file_info.file_path) as img:
            fmt = img.format or "UNKNOWN"
            # PIL returns "PNG" for APNG; use multi-frame detection to distinguish
            if fmt == "PNG" and is_animated(img):
                fmt = "APNG"
            mode = img.mode
            result = {
                "width": img.width,
                "height": img.height,
                "format": fmt,
                "mode": mode,
                "file_size": file_info.file_size,
            }

        if include_palette and (fmt == "GIF" or mode == "P"):
            result["palette_size"] = count_gif_colors(
                file_info.file_path, max_sample_pixels=self._PALETTE_SAMPLE_BUDGET)

        return result

    async def submit_convert(
        self,
        file_id: str,
        output_format: str = "png",
        quality: int = 85,
        width: Optional[int] = None,
        height: Optional[int] = None,
        scale: Optional[float] = None,
        coalesce: bool = False,
        suppress_results: Optional[bool] = None,
    ) -> str:
        """Submit an image conversion task."""
        file_info = self._file_service.require_file(file_id)

        params = {
            "file_id": file_id,
            "output_format": output_format,
            "quality": quality,
            "width": width,
            "height": height,
            "scale": scale,
            "coalesce": coalesce,
        }

        task_id = await self._task_manager.submit(TASK_TYPE_IMAGE_CONVERT, params,
                                                  suppress_results=suppress_results)
        logger.info(f"Image convert task submitted: {task_id}")

        return task_id

    def _handle_task(
        self,
        params: dict,
        progress_callback: Callable[[float, str], None]
    ) -> dict:
        """Handle conversion task (synchronous)."""
        return self._execute(params, progress_callback)

    def _execute(
        self,
        params: dict,
        progress_callback: Callable[[float, str], None]
    ) -> dict:
        """Execute image format conversion."""
        file_id = params["file_id"]
        file_info = self._file_service.require_file(file_id)

        from app.utils.gif_utils import animation_format, apply_and_save

        progress_callback(0.1, "task.progress.loading_image")

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
            # Keep animation: output format matches source animation format
            keep_anim_fmt = src_anim_fmt if (
                src_anim_fmt and (
                    (src_anim_fmt == "GIF" and output_format == "GIF") or
                    (src_anim_fmt == "PNG" and output_format == "PNG")
                )
            ) else None
            if not keep_anim_fmt:
                img = raw.copy()
                # Handle RGBA to RGB conversion (JPEG doesn't support alpha)
                if output_format in ["JPEG", "JPG"] and img.mode in ["RGBA", "P"]:
                    img = img.convert("RGB")

        if not keep_anim_fmt:
            progress_callback(0.3, "task.progress.resizing")
            img = _resize_frame(img)

        progress_callback(0.6, "task.progress.converting_format")

        # Build output path
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

        output_file_id, output_path = self._file_service.create_output_path(
            original_filename=file_info.original_filename,
            suffix="_converted",
            ext=f".{ext}",
        )

        progress_callback(0.8, "task.progress.saving_file")

        if keep_anim_fmt:
            def _anim_progress(p: float, msg: str) -> None:
                progress_callback(0.1 + p * 0.5, msg)

            with Image.open(file_info.file_path) as raw_anim:
                apply_and_save(
                    raw_anim,
                    output_path,
                    _resize_frame,
                    on_progress=_anim_progress,
                    preserve_alpha=False,
                )
        else:
            # Save options
            save_kwargs: dict = {}
            if output_format in ["JPEG", "JPG", "WEBP"]:
                save_kwargs["quality"] = params.get("quality", 85)
            if output_format == "PNG":
                save_kwargs["optimize"] = True

            save_format = output_format
            if output_format == "JPG":
                save_format = "JPEG"

            img.save(str(output_path), format=save_format, **save_kwargs)
            img.close()

        # Coalesce post-processing: expand frame-diffs → full frames (GIF compatibility)
        if output_format == "GIF" and params.get("coalesce") and self._gifsicle is not None:
            self._gifsicle.compress(output_path, output_path, coalesce=True)

        # Register output file
        output_info = self._file_service.register_output(
            file_id=output_file_id,
            file_path=output_path,
            original_filename=file_info.original_filename,
        )

        progress_callback(1.0, "task.progress.convert_complete")

        return {
            "output_file_id": output_file_id,
            "output_filename": output_info.filename,
            "output_size": output_info.file_size,
        }
