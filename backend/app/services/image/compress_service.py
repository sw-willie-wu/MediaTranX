"""Image compression service (same-format size reduction)."""
import logging
from pathlib import Path
from typing import Callable

from app.adapters.binary.gifsicle import GifsicleWrapper
from app.services.files.file_service import FileService
from app.utils.png_compress import compress_png
from app.workers.task_manager import TaskManager

logger = logging.getLogger(__name__)
TASK_TYPE_IMAGE_COMPRESS = "image.compress"

_EXT_BY_FMT = {"JPEG": "jpg", "JPG": "jpg", "PNG": "png", "GIF": "gif", "WEBP": "webp"}


class ImageCompressService:
    def __init__(self, file_service: FileService, task_manager: TaskManager,
                 gifsicle: GifsicleWrapper):
        self._files = file_service
        self._tm = task_manager
        self._gifsicle = gifsicle
        self._tm.register_handler(TASK_TYPE_IMAGE_COMPRESS, self._handle_task,
                                  output_policy="history")
        logger.info("ImageCompressService initialized")

    async def submit_compress(self, file_id: str, strength: int = 60,
                              suppress_results: bool = False, **opts) -> str:
        self._files.require_file(file_id)
        params = {"file_id": file_id, "strength": strength, **opts}
        return await self._tm.submit(TASK_TYPE_IMAGE_COMPRESS, params,
                                     suppress_results=suppress_results)

    def _handle_task(self, params, progress_callback):
        return self._execute(params, progress_callback)

    def _execute(self, params: dict, progress_callback: Callable[[float, str], None]) -> dict:
        from PIL import Image
        info = self._files.require_file(params["file_id"])
        src = Path(info.file_path)
        strength = int(params.get("strength", 60))
        progress_callback(0.1, "task.progress.image_compress_loading")

        with Image.open(src) as im:
            fmt = (im.format or "").upper()
        ext = _EXT_BY_FMT.get(fmt)
        if ext is None:
            raise ValueError(f"compress: unsupported format {fmt}")

        out_id, out_path = self._files.create_output_path(
            original_filename=info.original_filename, suffix="_compressed", ext=f".{ext}")
        progress_callback(0.4, "task.progress.image_compress_processing")

        if fmt == "GIF":
            from app.utils.gif_colors import count_gif_colors
            actual = count_gif_colors(src)
            gc = params.get("gif_colors")
            colors = gc if (gc and gc < actual) else None  # avoid None<int TypeError + --colors=0
            lossy = int(strength * 2)
            self._gifsicle.compress(
                src, out_path, lossy=lossy,
                colors=colors,
                frame_drop=int(params.get("gif_frame_drop", 0)),
                optimize_transparency=bool(params.get("gif_optimize_transparency", True)),
                coalesce=False)
        elif fmt == "PNG":
            compress_png(src, out_path, lossy=bool(params.get("png_lossy", True)),
                         strength=strength)
        elif fmt in ("JPEG", "JPG"):
            self._save_jpeg(src, out_path, strength, params)
        elif fmt == "WEBP":
            self._save_webp(src, out_path, strength, params)

        # P3 — never-grow guard (all formats): if output is not smaller, keep the original
        import shutil
        import os
        already_optimal = False
        if os.path.getsize(out_path) >= info.file_size:
            shutil.copyfile(src, out_path)
            already_optimal = True

        progress_callback(0.9, "task.progress.image_compress_saving")
        out = self._files.register_output(file_id=out_id, file_path=out_path,
                                          original_filename=info.original_filename)
        progress_callback(1.0, "task.progress.image_compress_complete")
        orig = info.file_size
        return {
            "output_file_id": out_id, "output_filename": out.filename,
            "output_size": out.file_size, "original_size": orig,
            "saved_ratio": round(1 - out.file_size / orig, 4) if orig else 0.0,
            "already_optimal": already_optimal,
        }

    def _save_jpeg(self, src, dst, strength, params):
        from PIL import Image
        q = max(20, 95 - int(strength * 0.65))
        with Image.open(src) as im:
            im = im.convert("RGB")
            save_kwargs = {"quality": q, "optimize": True,
                           "progressive": bool(params.get("jpeg_progressive", True))}
            if not params.get("jpeg_keep_metadata", False):
                im.info.pop("exif", None)
            im.save(dst, format="JPEG", **save_kwargs)

    def _save_webp(self, src, dst, strength, params):
        from PIL import Image
        with Image.open(src) as im:
            if params.get("webp_lossless", False):
                im.save(dst, format="WEBP", lossless=True, method=6)
            else:
                q = max(20, 95 - int(strength * 0.65))
                im.save(dst, format="WEBP", quality=q, method=6)
