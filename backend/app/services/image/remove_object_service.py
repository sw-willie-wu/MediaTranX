"""
AI 物件移除服務（MobileSAM + LaMa Inpainting）
"""
from __future__ import annotations

import base64
import io
import logging
from pathlib import Path
from typing import Callable, Optional
from uuid import uuid4

from app.services.files.file_service import FileService
from app.workers.task_manager import TaskManager

logger = logging.getLogger(__name__)

TASK_TYPE_IMAGE_REMOVE_OBJECT = "image.remove_object"


class ImageRemoveObjectService:

    def __init__(self, file_service: FileService, task_manager: TaskManager):
        self._file_service = file_service
        self._task_manager = task_manager
        self._lama_model = None
        self._task_manager.register_handler(TASK_TYPE_IMAGE_REMOVE_OBJECT, self._handle_remove_object_task)
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
        """用 LaMa 填補遮罩區域（裁切包圍框處理，支援大圖），fallback 至 OpenCV。"""
        import numpy as np
        from PIL import Image
        LAMA_MAX_SIZE = 1024  # LaMa 最大處理邊長

        try:
            self._load_lama()
            img_rgb = image_pil.convert("RGB")
            mask_l = mask_pil.convert("L")
            mask_np = np.array(mask_l)
            orig_np = np.array(img_rgb)
            H, W = orig_np.shape[:2]

            # 找遮罩包圍框
            ys, xs = np.where(mask_np > 127)
            if len(ys) == 0:
                return image_pil

            mask_w = int(xs.max()) - int(xs.min())
            mask_h = int(ys.max()) - int(ys.min())
            # context pad = 遮罩短邊的一半，至少 64px，讓 LaMa 看到足夠背景
            context_pad = max(64, mask_w // 2, mask_h // 2)

            x1 = max(0, int(xs.min()) - context_pad)
            y1 = max(0, int(ys.min()) - context_pad)
            x2 = min(W, int(xs.max()) + context_pad)
            y2 = min(H, int(ys.max()) + context_pad)

            # 裁切出感興趣區域
            crop_img = img_rgb.crop((x1, y1, x2, y2))
            crop_mask = mask_l.crop((x1, y1, x2, y2))

            # 若裁切後仍過大，等比縮小
            cw, ch = crop_img.size
            scale = 1.0
            if max(cw, ch) > LAMA_MAX_SIZE:
                scale = LAMA_MAX_SIZE / max(cw, ch)
                new_w, new_h = int(cw * scale), int(ch * scale)
                crop_img = crop_img.resize((new_w, new_h), Image.LANCZOS)
                crop_mask = crop_mask.resize((new_w, new_h), Image.NEAREST)

            logger.info(f"LaMa: crop=({x1},{y1},{x2},{y2}) scale={scale:.2f} size={crop_img.size}")

            # simple_lama_inpainting bug: mask_t 是 Long，需轉 float
            from simple_lama_inpainting.utils.util import prepare_img_and_mask
            import torch
            lama = self._lama_model
            image_t, mask_t = prepare_img_and_mask(crop_img, crop_mask, lama.device)
            mask_t = mask_t.float()
            with torch.inference_mode():
                inpainted = lama.model(image_t, mask_t)
            raw = inpainted[0].permute(1, 2, 0).cpu().numpy()
            lama_crop = Image.fromarray(np.clip(raw * 255, 0, 255).astype(np.uint8))

            # LaMa 會 pad 輸入到 8 的倍數，輸出可能比輸入寬/高，需裁切回 crop 尺寸
            lama_crop = lama_crop.crop((0, 0, crop_img.width, crop_img.height))

            # 若有縮放，還原尺寸
            if scale < 1.0:
                lama_crop = lama_crop.resize((cw, ch), Image.LANCZOS)
                orig_crop_mask = mask_l.crop((x1, y1, x2, y2))
            else:
                orig_crop_mask = crop_mask

            # 合成：遮罩內用 LaMa 結果，遮罩外保留原圖
            crop_mask_np = np.array(orig_crop_mask).astype(np.float32) / 255.0
            crop_orig_np = np.array(img_rgb.crop((x1, y1, x2, y2))).astype(np.float32)
            crop_result_np = np.array(lama_crop).astype(np.float32)
            blended_crop = (crop_result_np * crop_mask_np[..., np.newaxis] +
                            crop_orig_np * (1.0 - crop_mask_np[..., np.newaxis])).astype(np.uint8)

            # 貼回完整圖
            result = img_rgb.copy()
            result.paste(Image.fromarray(blended_crop), (x1, y1))
            return result

        except Exception as e:
            logger.warning(f"LaMa failed ({e})，fallback 至 OpenCV inpainting")
            import cv2
            img_bgr = cv2.cvtColor(np.array(image_pil.convert("RGB")), cv2.COLOR_RGB2BGR)
            mask_cv = (np.array(mask_pil.convert("L")) > 127).astype(np.uint8) * 255
            result_bgr = cv2.inpaint(img_bgr, mask_cv, 10, cv2.INPAINT_TELEA)
            return Image.fromarray(cv2.cvtColor(result_bgr, cv2.COLOR_BGR2RGB))

    def _decode_mask(self, mask_data: str, target_w: int, target_h: int):
        import numpy as np
        from PIL import Image
        if "," in mask_data:
            mask_data = mask_data.split(",")[1]
        mask_bytes = base64.b64decode(mask_data)
        mask_img = Image.open(io.BytesIO(mask_bytes)).convert("L")
        mask_img = mask_img.resize((target_w, target_h), Image.NEAREST)
        return np.array(mask_img)

    def _refine_with_sam(self, image_rgb, rough_mask):
        import numpy as np

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

    def _handle_remove_object_task(self, params: dict, progress_callback: Callable) -> dict:
        file_id = params["file_id"]
        mask_data = params["mask_data"]

        file_info = self._file_service.get_file(file_id)

        import numpy as np
        from PIL import Image

        with Image.open(file_info.file_path) as img:
            img = img.copy()

        # 保留 alpha 通道，inpaint 只處理 RGB
        # 統一轉 RGBA 以支援 P/PA/LA 等所有含透明資訊的模式
        img_rgba = img.convert("RGBA")
        alpha_channel = img_rgba.split()[3]
        has_alpha = alpha_channel.getextrema()[0] < 255
        if not has_alpha:
            alpha_channel = None
        img_rgb = img_rgba.convert("RGB")

        image_rgb = np.array(img_rgb)
        h, w = image_rgb.shape[:2]

        progress_callback(0.1, "解析遮罩...")
        rough_mask = self._decode_mask(mask_data, w, h)

        # === GPU 排隊管線 ===
        from app.init.container import get_container
        manager = get_container().model_manager()

        with manager.gpu_session():
            # 略微膨脹筆刷遮罩（填補筆觸縫隙），直接送 LaMa（跳過 SAM，避免遮罩過大）
            progress_callback(0.35, "處理遮罩...")
            import cv2 as _cv2
            kernel = _cv2.getStructuringElement(_cv2.MORPH_ELLIPSE, (15, 15))
            precise_mask = _cv2.dilate(rough_mask, kernel, iterations=2)

            progress_callback(0.6, "填補背景中...")
            mask_pil = Image.fromarray(precise_mask).convert("L")
            result_img = self._run_inpaint(img_rgb, mask_pil)

        # 還原 alpha 通道
        if alpha_channel is not None:
            result_rgba = result_img.convert("RGBA")
            result_rgba.putalpha(alpha_channel)
            result_img = result_rgba

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
        return target_dir / f"{Path(file_info.original_filename).stem}_removed_{uuid4().hex[:8]}.png"
