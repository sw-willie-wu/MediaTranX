"""Image super-resolution and enhancement service."""
import logging
from pathlib import Path
from typing import Callable, Optional

from PIL import Image

from app.engine.ai.model_manager import ModelManager
from app.services.files.file_service import FileService
from app.workers.task_manager import TaskManager
logger = logging.getLogger(__name__)

TASK_TYPE_IMAGE_UPSCALE = "image.upscale"

_UPSCALE_FAMILIES = ["real-cugan", "realesrgan", "swinir", "bsrgan", "waifu2x"]
_FACE_FAMILIES = ["codeformer", "gfpgan"]


def _parse_model_id(model_id: str, known_families: list) -> tuple:
    """Parse (family, variant) from model_id, matching by longest family prefix."""
    for family in sorted(known_families, key=len, reverse=True):
        prefix = family + "-"
        if model_id.startswith(prefix):
            variant = model_id[len(prefix):]
            return family, variant
    raise ValueError(f"Unknown model_id: {model_id}. Known families: {known_families}")


class ImageUpscaleService:
    """Image super-resolution using Real-ESRGAN / Real-CUGAN / SwinIR / BSRGAN models."""

    def __init__(self, file_service: FileService, task_manager: TaskManager,
                 model_manager: ModelManager):
        self._file_service = file_service
        self._task_manager = task_manager
        self._model_manager = model_manager

        self._task_manager.register_handler(
            TASK_TYPE_IMAGE_UPSCALE,
            self._handle_task,
            output_policy="history",
        )

        logger.info("ImageUpscaleService initialized")

    async def submit_upscale(
        self,
        file_id: str,
        model_id: str = "realesrgan-x4plus",
        scale: int = 4,
        sharpen: bool = False,
        face_fix: bool = False,
        face_restore_model_id: Optional[str] = None,
        face_restore_fidelity: float = 0.7,
        face_restore_upscale: int = 2,
    ) -> str:
        file_info = self._file_service.require_file(file_id)

        task_id = await self._task_manager.submit(TASK_TYPE_IMAGE_UPSCALE, {
            "file_id": file_id,
            "model_id": model_id,
            "scale": scale,
            "sharpen": sharpen,
            "face_fix": face_fix,
            "face_restore_model_id": face_restore_model_id,
            "face_restore_fidelity": face_restore_fidelity,
            "face_restore_upscale": face_restore_upscale,
        })
        logger.info(f"Image upscale task submitted: {task_id}")
        return task_id

    def _handle_task(self, params: dict, progress_callback: Callable[[float, str], None]) -> dict:
        return self._execute(params, progress_callback)

    def _execute(self, params: dict, progress_callback: Callable[[float, str], None]) -> dict:
        file_id  = params["file_id"]
        model_id = params["model_id"]
        scale    = params["scale"]
        face_fix = params.get("face_fix", False)
        face_restore_model_id = params.get("face_restore_model_id")

        file_info = self._file_service.require_file(file_id)

        # === GPU queue pipeline ===
        with self._model_manager.gpu_session():
            # -- Super-resolution --
            upscale_family, upscale_variant = _parse_model_id(model_id, _UPSCALE_FAMILIES)
            progress_callback(0.05, f"task.progress.load_model|{model_id}")

            from app.engine.ai.image import get_upscaler
            upscaler = get_upscaler(upscale_family)

            # Query the model's native scale
            from app.engine.ai.registry import MODELS_REGISTRY, FORMAT_PTH
            native_scale = MODELS_REGISTRY.get(FORMAT_PTH, {}).get(upscale_family, {}).get(
                "variants", {}
            ).get(upscale_variant, {}).get("scale", 4)

            from app.utils.gif_utils import animation_format, extract_frames, save_animated, animation_ext

            upscale_end = 0.7 if face_fix else 0.85

            from app.utils.image_alpha import preserve_alpha

            def _upscale_single(img: Image.Image, progress_start: float, progress_end: float) -> Image.Image:
                """Upscale one frame, preserving alpha if present."""
                span = progress_end - progress_start

                def _upscale_rgb(rgb: Image.Image) -> Image.Image:
                    result = upscaler.enhance(
                        rgb,
                        model_id=upscale_variant,
                        scale=native_scale,
                        on_progress=lambda p, m: progress_callback(
                            progress_start + (0.05 + p * 0.35 if p <= 1.0 else 0.40 + (p - 1.0) * 0.30) * span,
                            m,
                        ),
                    )
                    if scale < native_scale:
                        orig_w, orig_h = rgb.size
                        result = result.resize((orig_w * scale, orig_h * scale), Image.LANCZOS)
                    return result

                return preserve_alpha(img, _upscale_rgb)

            with Image.open(file_info.file_path) as raw:
                anim_fmt = animation_format(raw)
                if anim_fmt:
                    frames = extract_frames(raw)
                    total = len(frames)
                    result_frames = []
                    for i, (frame, duration) in enumerate(frames):
                        progress_callback(0.05 + i / total * 0.60, f"task.progress.upscale_frame|{i + 1}|{total}")
                        result_frame = _upscale_single(frame, 0.0, 1.0 / total)
                        result_frames.append((result_frame, duration))
                else:
                    img = raw.copy()
                    result_img = _upscale_single(img, 0.0, 1.0)

            progress_callback(upscale_end, "task.progress.upscale_complete")

            # -- Face restoration (optional, static images only) --
            if not anim_fmt and face_fix and face_restore_model_id:
                try:
                    face_family, face_variant = _parse_model_id(face_restore_model_id, _FACE_FAMILIES)
                    fidelity = params.get("face_restore_fidelity", 0.7)
                    face_upscale = params.get("face_restore_upscale", 2)
                    progress_callback(0.75, f"task.progress.load_face_model|{face_restore_model_id}")

                    from app.engine.ai.image import get_face_restorer
                    restorer = get_face_restorer(face_family)

                    restore_kwargs: dict = {"model_id": face_variant, "on_progress": lambda p, m: progress_callback(0.75 + p * 0.15, m)}
                    if face_family == "codeformer":
                        restore_kwargs["fidelity"] = fidelity
                    elif face_family == "gfpgan":
                        restore_kwargs["upscale"] = face_upscale

                    result_img = restorer.restore(result_img, **restore_kwargs)
                except Exception as e:
                    logger.warning(f"Face restore failed, returning upscaled image only: {e}")

        output_file_id, output_path = self._file_service.create_output_path(
            original_filename=file_info.original_filename,
            suffix=f"_x{scale}",
            ext=".png",
        )
        if anim_fmt:
            output_path = output_path.with_suffix(animation_ext(anim_fmt))
            save_animated(result_frames, output_path, anim_fmt)
        else:
            result_img.save(output_path, "PNG")

        progress_callback(0.95, "task.progress.registering")
        output_info = self._file_service.register_output(
            file_id=output_file_id,
            file_path=output_path,
            original_filename=file_info.original_filename,
        )

        progress_callback(1.0, "task.progress.upscale_complete")
        return {
            "output_file_id": output_file_id,
            "output_filename": output_info.filename,
            "scale": scale,
        }

