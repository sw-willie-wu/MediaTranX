"""Image adjustment service."""
from __future__ import annotations

import hashlib
import logging
from functools import lru_cache
from typing import Callable

import numpy as np
from PIL import Image, ImageEnhance, ImageFilter

from app.services.files.file_service import FileService
from app.workers.task_manager import TaskManager

logger = logging.getLogger(__name__)

TASK_TYPE_IMAGE_FILTER = "image.filter"


class ImageFilterService:
    """Image adjustment service for brightness, contrast, hue, effects, and more."""

    def __init__(self, file_service: FileService, task_manager: TaskManager):
        self._file_service = file_service
        self._task_manager = task_manager

        self._task_manager.register_handler(
            TASK_TYPE_IMAGE_FILTER,
            self._handle_task,
            output_policy="history",
        )

        logger.info("ImageFilterService initialized")

    async def submit_filter(
        self,
        file_id:    str,
        brightness: float = 1.0,
        contrast:   float = 1.0,
        saturation: float = 1.0,
        hue:        float = 0.0,
        sharpness:  float = 1.0,
        warmth:     float = 0.0,
        grayscale:  float = 0.0,
        sepia:      float = 0.0,
        invert:     float = 0.0,
        blur:       float = 0.0,
        vignette:   float = 0.0,
        suppress_results: bool = False,
    ) -> str:
        """Submit an image adjustment task."""
        file_info = self._file_service.require_file(file_id)

        params = {
            "file_id":    file_id,
            "brightness": brightness,
            "contrast":   contrast,
            "saturation": saturation,
            "hue":        hue,
            "sharpness":  sharpness,
            "warmth":     warmth,
            "grayscale":  grayscale,
            "sepia":      sepia,
            "invert":     invert,
            "blur":       blur,
            "vignette":   vignette,
        }

        task_id = await self._task_manager.submit(TASK_TYPE_IMAGE_FILTER, params,
                                                  suppress_results=suppress_results)
        logger.info(f"Image filter task submitted: {task_id}")
        return task_id

    def _handle_task(
        self,
        params: dict,
        progress_callback: Callable[[float, str], None],
    ) -> dict:
        return self._execute(params, progress_callback)

    # -- Adjustment methods --

    @staticmethod
    def _apply_hue(img: Image.Image, degrees: float) -> Image.Image:
        """Hue rotation (vectorized HSV conversion)."""
        if degrees == 0:
            return img

        arr = np.array(img.convert("RGB"), dtype=np.float32) / 255.0
        r, g, b = arr[:, :, 0], arr[:, :, 1], arr[:, :, 2]

        cmax  = np.maximum(np.maximum(r, g), b)
        cmin  = np.minimum(np.minimum(r, g), b)
        delta = cmax - cmin
        eps   = 1e-6

        v = cmax
        s = np.where(cmax > eps, delta / cmax, 0.0)

        h = np.zeros_like(cmax)
        mr = (cmax == r) & (delta > eps)
        mg = (cmax == g) & (delta > eps)
        mb = (cmax == b) & (delta > eps)
        h[mr] = ((g[mr] - b[mr]) / delta[mr]) % 6
        h[mg] = (b[mg] - r[mg]) / delta[mg] + 2
        h[mb] = (r[mb] - g[mb]) / delta[mb] + 4
        h /= 6.0
        h = (h + degrees / 360.0) % 1.0

        h6   = h * 6.0
        i    = np.floor(h6).astype(np.int32)
        f    = h6 - i
        p    = v * (1 - s)
        q    = v * (1 - s * f)
        t    = v * (1 - s * (1 - f))
        im   = i % 6

        r2 = np.select([im==0, im==1, im==2, im==3, im==4, im==5], [v, q, p, p, t, v])
        g2 = np.select([im==0, im==1, im==2, im==3, im==4, im==5], [t, v, v, q, p, p])
        b2 = np.select([im==0, im==1, im==2, im==3, im==4, im==5], [p, p, t, v, v, q])

        result = np.clip(np.stack([r2, g2, b2], axis=2) * 255, 0, 255).astype(np.uint8)
        return Image.fromarray(result, "RGB")

    @staticmethod
    def _apply_warmth(img: Image.Image, warmth: float) -> Image.Image:
        """Color temperature adjustment (positive=warm, negative=cool)."""
        if warmth == 0:
            return img

        arr = np.array(img.convert("RGB"), dtype=np.float32)
        if warmth > 0:
            arr[:, :, 0] = np.clip(arr[:, :, 0] + warmth * 30, 0, 255)
            arr[:, :, 2] = np.clip(arr[:, :, 2] - warmth * 20, 0, 255)
        else:
            arr[:, :, 0] = np.clip(arr[:, :, 0] + warmth * 20, 0, 255)
            arr[:, :, 2] = np.clip(arr[:, :, 2] - warmth * 30, 0, 255)

        return Image.fromarray(arr.astype(np.uint8), "RGB")

    @staticmethod
    def _apply_sepia(img: Image.Image, intensity: float) -> Image.Image:
        """Sepia tone effect."""
        if intensity <= 0:
            return img

        arr = np.array(img.convert("RGB"), dtype=np.float32)
        r, g, b = arr[:, :, 0], arr[:, :, 1], arr[:, :, 2]

        sr = np.clip(r * 0.393 + g * 0.769 + b * 0.189, 0, 255)
        sg = np.clip(r * 0.349 + g * 0.686 + b * 0.168, 0, 255)
        sb = np.clip(r * 0.272 + g * 0.534 + b * 0.131, 0, 255)

        sepia_arr = np.stack([sr, sg, sb], axis=2)
        result = arr * (1 - intensity) + sepia_arr * intensity
        return Image.fromarray(result.astype(np.uint8), "RGB")

    @staticmethod
    def _apply_invert(img: Image.Image, intensity: float) -> Image.Image:
        """Invert (negative) effect."""
        if intensity <= 0:
            return img

        arr      = np.array(img.convert("RGB"), dtype=np.float32)
        inverted = 255 - arr
        result   = arr * (1 - intensity) + inverted * intensity
        return Image.fromarray(result.astype(np.uint8), "RGB")

    @staticmethod
    def _apply_vignette(img: Image.Image, intensity: float) -> Image.Image:
        """Vignette effect (radial gradient darkening)."""
        if intensity <= 0:
            return img

        w, h = img.size
        Y, X = np.ogrid[:h, :w]
        cx, cy = w / 2.0, h / 2.0

        dist    = np.sqrt(((X - cx) / (w / 2.0)) ** 2 + ((Y - cy) / (h / 2.0)) ** 2)
        spread  = max(0.01, 1.0 - intensity * 0.6)
        mask    = np.clip((dist - spread) / (1.0 - spread + 1e-6), 0, 1)
        darken  = 1.0 - mask * intensity * 0.85

        arr          = np.array(img.convert("RGB"), dtype=np.float32)
        arr[:, :, 0] *= darken
        arr[:, :, 1] *= darken
        arr[:, :, 2] *= darken

        return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGB")

    # -- Preview (synchronous, reduced resolution) --

    # LRU cache for base thumbnails — avoids re-reading & resizing on every slider drag
    # Stores (RGB bytes, alpha bytes | None) so alpha compositing can be done per-preview.
    @staticmethod
    @lru_cache(maxsize=8)
    def _load_preview_thumb(file_path: str, max_size: int) -> tuple[bytes, bytes | None]:
        """Load and thumbnail image, return (PNG rgb bytes, PNG alpha bytes | None)."""
        import io
        raw = Image.open(file_path)
        raw.thumbnail((max_size, max_size), Image.LANCZOS)

        has_alpha = raw.mode in ("RGBA", "LA", "PA") or (
            raw.mode == "P" and "transparency" in raw.info
        )
        rgba = raw.convert("RGBA") if has_alpha else None
        rgb = raw.convert("RGB")

        buf_rgb = io.BytesIO()
        rgb.save(buf_rgb, format="PNG")

        buf_alpha: bytes | None = None
        if rgba is not None:
            alpha = rgba.split()[3]
            buf_a = io.BytesIO()
            alpha.save(buf_a, format="PNG")
            buf_alpha = buf_a.getvalue()

        return buf_rgb.getvalue(), buf_alpha

    def generate_preview(self, file_id: str, params: dict, max_size: int = 900) -> str:
        """Generate preview synchronously: thumbnail then apply all effects, return base64 JPEG/PNG string."""
        import base64
        import io

        file_info = self._file_service.require_file(file_id)

        # Use cached thumbnail to avoid repeated disk I/O + resize
        rgb_bytes, alpha_bytes = self._load_preview_thumb(str(file_info.file_path), max_size)
        img = Image.open(io.BytesIO(rgb_bytes)).convert("RGB")

        # Apply same effect order as _execute (no progress callback needed)
        def noop(_p, _m): pass
        img = self._apply_all(img, params, noop)

        buf = io.BytesIO()
        if alpha_bytes is not None:
            # Preserve transparency: composite back to RGBA after effects, output PNG
            alpha = Image.open(io.BytesIO(alpha_bytes)).convert("L")
            out = img.convert("RGBA")
            out.putalpha(alpha)
            out.save(buf, format="PNG")
            mime = "image/png"
        else:
            img.save(buf, format="JPEG", quality=75)
            mime = "image/jpeg"
        return f"data:{mime};base64," + base64.b64encode(buf.getvalue()).decode()

    def _apply_all(self, img: Image.Image, params: dict, progress_callback) -> Image.Image:
        """Apply all adjustments (shared by generate_preview and _execute)."""
        grayscale = params.get("grayscale", 0.0)
        if grayscale > 0:
            gray = img.convert("L").convert("RGB")
            if grayscale >= 1.0:
                img = gray
            else:
                arr_orig = np.array(img, dtype=np.float32)
                arr_gray = np.array(gray, dtype=np.float32)
                img = Image.fromarray(
                    np.clip(arr_orig * (1 - grayscale) + arr_gray * grayscale, 0, 255).astype(np.uint8), "RGB"
                )

        brightness = params.get("brightness", 1.0)
        if brightness != 1.0:
            img = ImageEnhance.Brightness(img).enhance(brightness)

        contrast = params.get("contrast", 1.0)
        if contrast != 1.0:
            img = ImageEnhance.Contrast(img).enhance(contrast)

        saturation = params.get("saturation", 1.0)
        if saturation != 1.0:
            img = ImageEnhance.Color(img).enhance(saturation)

        progress_callback(0.35, "task.progress.applying_color")

        hue = params.get("hue", 0.0)
        if hue != 0:
            img = self._apply_hue(img, hue)

        warmth = params.get("warmth", 0.0)
        if warmth != 0:
            img = self._apply_warmth(img, warmth)

        sharpness = params.get("sharpness", 1.0)
        if sharpness != 1.0:
            img = ImageEnhance.Sharpness(img).enhance(sharpness)

        progress_callback(0.55, "task.progress.applying_filter")

        sepia = params.get("sepia", 0.0)
        if sepia > 0:
            img = self._apply_sepia(img, sepia)

        invert = params.get("invert", 0.0)
        if invert > 0:
            img = self._apply_invert(img, invert)

        blur = params.get("blur", 0.0)
        if blur > 0:
            img = img.filter(ImageFilter.GaussianBlur(radius=blur))

        vignette = params.get("vignette", 0.0)
        if vignette > 0:
            img = self._apply_vignette(img, vignette)

        return img

    # -- Main execution flow --

    def _execute(
        self,
        params: dict,
        progress_callback: Callable[[float, str], None],
    ) -> dict:
        file_id   = params["file_id"]
        file_info = self._file_service.require_file(file_id)

        from app.utils.gif_utils import animation_format, apply_and_save, animation_ext

        progress_callback(0.05, "task.progress.loading_image")

        def noop(p, m): pass

        # frame_fn receives the RGB view (preserve_alpha=True in apply_and_save handles stripping/restoring alpha)
        def _frame_fn(rgb: Image.Image) -> Image.Image:
            return self._apply_all(rgb, params, noop)

        with Image.open(file_info.file_path) as raw:
            anim_fmt = animation_format(raw)

        ext = animation_ext(anim_fmt).lstrip(".") if anim_fmt else "png"
        # Save adjusted results to system temp dir; user chooses final location on download
        output_file_id, output_path = self._file_service.create_output_path(
            original_filename=file_info.original_filename,
            suffix="_adjusted",
            ext=f".{ext}",
        )

        def _on_progress(p: float, msg: str) -> None:
            # animation: scale per-frame progress into 0.15–0.75 band
            progress_callback(0.15 + p * 0.6, msg)

        if not anim_fmt:
            progress_callback(0.15, "task.progress.applying_adjustment_single")

        with Image.open(file_info.file_path) as raw:
            apply_and_save(
                raw,
                output_path,
                _frame_fn,
                on_progress=_on_progress if anim_fmt else None,
                preserve_alpha=True,
                static_save_kwargs={"format": "PNG"},
            )

        progress_callback(0.9, "task.progress.saving_file")

        output_info = self._file_service.register_output(
            file_id=output_file_id,
            file_path=output_path,
            original_filename=file_info.original_filename,
        )

        progress_callback(1.0, "task.progress.adjustment_complete")
        logger.info("Image filter completed: %s → %s", file_id, output_file_id)

        return {
            "output_file_id":  output_file_id,
            "output_filename": output_info.filename,
        }
