"""AI object removal service (MobileSAM + LaMa Inpainting)."""
from __future__ import annotations

import base64
import io
import logging
from pathlib import Path
from typing import Callable, Optional
from uuid import uuid4

import cv2
import numpy as np
import torch
from PIL import Image

from app.services.files.file_service import FileService
from app.workers.task_manager import TaskManager

logger = logging.getLogger(__name__)

TASK_TYPE_IMAGE_REMOVE_OBJECT = "image.remove_object"


class ImageRemoveObjectService:
    """AI object removal using MobileSAM segmentation and LaMa inpainting."""

    def __init__(self, file_service: FileService, task_manager: TaskManager):
        self._file_service = file_service
        self._task_manager = task_manager
        self._lama_model = None
        self._task_manager.register_handler(TASK_TYPE_IMAGE_REMOVE_OBJECT, self._handle_task)
        logger.info("ImageRemoveObjectService initialized")

    async def submit_remove_object(
        self,
        file_id: str,
        mask_data: str,
        output_dir: Optional[str] = None,
    ) -> str:
        file_info = self._file_service.get_file(file_id)
        if not file_info:
            raise ValueError(f"File not found: {file_id}")
        task_id = await self._task_manager.submit(TASK_TYPE_IMAGE_REMOVE_OBJECT, {
            "file_id": file_id,
            "mask_data": mask_data,
            "output_dir": output_dir,
        })
        logger.info(f"Image remove-object task submitted: {task_id}")
        return task_id

    def _get_mobilesam(self):
        from app.engine.ai.image.mobilesam import get_mobilesam
        return get_mobilesam()

    def _load_lama(self):
        if self._lama_model is not None:
            return
        from simple_lama_inpainting import SimpleLama
        self._lama_model = SimpleLama()
        logger.info("LaMa loaded")

    def _run_inpaint(self, image_pil: Image.Image, mask_pil: Image.Image) -> Image.Image:
        """Fill masked region with LaMa (bounding box crop, large image support), fallback to OpenCV."""
        LAMA_MAX_SIZE = 1024  # LaMa max processing dimension

        try:
            self._load_lama()
            img_rgb = image_pil.convert("RGB")
            mask_l = mask_pil.convert("L")
            mask_np = np.array(mask_l)
            orig_np = np.array(img_rgb)
            H, W = orig_np.shape[:2]

            # Find mask bounding box
            ys, xs = np.where(mask_np > 127)
            if len(ys) == 0:
                return image_pil

            mask_w = int(xs.max()) - int(xs.min())
            mask_h = int(ys.max()) - int(ys.min())
            # context pad = half of mask short side, at least 64px, for sufficient background context
            context_pad = max(64, mask_w // 2, mask_h // 2)

            x1 = max(0, int(xs.min()) - context_pad)
            y1 = max(0, int(ys.min()) - context_pad)
            x2 = min(W, int(xs.max()) + context_pad)
            y2 = min(H, int(ys.max()) + context_pad)

            # Crop region of interest
            crop_img = img_rgb.crop((x1, y1, x2, y2))
            crop_mask = mask_l.crop((x1, y1, x2, y2))

            # If cropped region is still too large, scale down proportionally
            cw, ch = crop_img.size
            scale = 1.0
            if max(cw, ch) > LAMA_MAX_SIZE:
                scale = LAMA_MAX_SIZE / max(cw, ch)
                new_w, new_h = int(cw * scale), int(ch * scale)
                crop_img = crop_img.resize((new_w, new_h), Image.LANCZOS)
                crop_mask = crop_mask.resize((new_w, new_h), Image.NEAREST)

            logger.info(f"LaMa: crop=({x1},{y1},{x2},{y2}) scale={scale:.2f} size={crop_img.size}")

            # simple_lama_inpainting bug: mask_t is Long, needs to be converted to float
            from simple_lama_inpainting.utils.util import prepare_img_and_mask
            lama = self._lama_model
            image_t, mask_t = prepare_img_and_mask(crop_img, crop_mask, lama.device)
            mask_t = mask_t.float()
            with torch.inference_mode():
                inpainted = lama.model(image_t, mask_t)
            raw = inpainted[0].permute(1, 2, 0).cpu().numpy()
            lama_crop = Image.fromarray(np.clip(raw * 255, 0, 255).astype(np.uint8))

            # LaMa pads input to multiples of 8; output may be larger than input, so crop back
            lama_crop = lama_crop.crop((0, 0, crop_img.width, crop_img.height))

            # If scaled, restore to original size
            if scale < 1.0:
                lama_crop = lama_crop.resize((cw, ch), Image.LANCZOS)
                orig_crop_mask = mask_l.crop((x1, y1, x2, y2))
            else:
                orig_crop_mask = crop_mask

            # Composite: use LaMa result inside mask, keep original outside
            crop_mask_np = np.array(orig_crop_mask).astype(np.float32) / 255.0
            crop_orig_np = np.array(img_rgb.crop((x1, y1, x2, y2))).astype(np.float32)
            crop_result_np = np.array(lama_crop).astype(np.float32)
            blended_crop = (crop_result_np * crop_mask_np[..., np.newaxis] +
                            crop_orig_np * (1.0 - crop_mask_np[..., np.newaxis])).astype(np.uint8)

            # Paste back into the full image
            result = img_rgb.copy()
            result.paste(Image.fromarray(blended_crop), (x1, y1))
            return result

        except Exception as e:
            logger.warning(f"LaMa failed ({e}), falling back to OpenCV inpainting")
            img_bgr = cv2.cvtColor(np.array(image_pil.convert("RGB")), cv2.COLOR_RGB2BGR)
            mask_cv = (np.array(mask_pil.convert("L")) > 127).astype(np.uint8) * 255
            result_bgr = cv2.inpaint(img_bgr, mask_cv, 10, cv2.INPAINT_TELEA)
            return Image.fromarray(cv2.cvtColor(result_bgr, cv2.COLOR_BGR2RGB))

    def _decode_mask(self, mask_data: str, target_w: int, target_h: int):
        if "," in mask_data:
            mask_data = mask_data.split(",")[1]
        mask_bytes = base64.b64decode(mask_data)
        mask_img = Image.open(io.BytesIO(mask_bytes)).convert("L")
        mask_img = mask_img.resize((target_w, target_h), Image.NEAREST)
        return np.array(mask_img)

    def _refine_with_sam(self, image_rgb, rough_mask):
        ys, xs = np.where(rough_mask > 127)
        if len(ys) == 0:
            return rough_mask

        pad = 10
        x1 = max(0, int(xs.min()) - pad)
        y1 = max(0, int(ys.min()) - pad)
        x2 = min(image_rgb.shape[1] - 1, int(xs.max()) + pad)
        y2 = min(image_rgb.shape[0] - 1, int(ys.max()) + pad)

        box = np.array([x1, y1, x2, y2])
        return self._get_mobilesam().predict_box(image_rgb, box)

    def _handle_task(self, params: dict, progress_callback: Callable[[float, str], None]) -> dict:
        return self._execute(params, progress_callback)

    def _execute(self, params: dict, progress_callback: Callable[[float, str], None]) -> dict:
        file_id = params["file_id"]
        mask_data = params["mask_data"]

        file_info = self._file_service.get_file(file_id)

        with Image.open(file_info.file_path) as img:
            img = img.copy()

        # Preserve alpha channel; inpaint only processes RGB
        # Convert to RGBA uniformly to support P/PA/LA and all modes with transparency
        img_rgba = img.convert("RGBA")
        alpha_channel = img_rgba.split()[3]
        has_alpha = alpha_channel.getextrema()[0] < 255
        if not has_alpha:
            alpha_channel = None
        img_rgb = img_rgba.convert("RGB")

        image_rgb = np.array(img_rgb)
        h, w = image_rgb.shape[:2]

        progress_callback(0.1, "task.progress.parsing_mask")
        rough_mask = self._decode_mask(mask_data, w, h)

        # === GPU queue pipeline ===
        from app.init.container import get_container
        manager = get_container().model_manager()

        with manager.gpu_session():
            # Slightly dilate brush mask (fill stroke gaps), send directly to LaMa (skip SAM to avoid oversized mask)
            progress_callback(0.35, "task.progress.processing_mask")
            kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (15, 15))
            precise_mask = cv2.dilate(rough_mask, kernel, iterations=2)

            progress_callback(0.6, "task.progress.inpainting")
            mask_pil = Image.fromarray(precise_mask).convert("L")
            result_img = self._run_inpaint(img_rgb, mask_pil)

        # Restore alpha channel
        if alpha_channel is not None:
            result_rgba = result_img.convert("RGBA")
            result_rgba.putalpha(alpha_channel)
            result_img = result_rgba

        output_file_id = str(uuid4())
        output_path = self._generate_output_path(file_info, params.get("output_dir"))

        progress_callback(0.9, "task.progress.saving_result")
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
        output_dir = Path(custom_dir) if custom_dir else self._file_service.output_dir
        output_dir.mkdir(parents=True, exist_ok=True)
        return output_dir / f"{Path(file_info.original_filename).stem}_removed_{uuid4().hex[:8]}.png"
