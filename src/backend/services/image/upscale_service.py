"""
圖片超解析與增強服務 (REFACTOR V4.1)
"""
import logging
from pathlib import Path
from typing import Callable, Optional
from uuid import uuid4
from PIL import Image

from backend.services.files.file_service import FileService, get_file_service
from backend.workers.task_manager import TaskManager, get_task_manager
logger = logging.getLogger(__name__)

TASK_TYPE_IMAGE_UPSCALE = "image.upscale"

_UPSCALE_FAMILIES = ["real-cugan", "realesrgan", "swinir", "bsrgan", "waifu2x"]
_FACE_FAMILIES = ["codeformer", "gfpgan"]


def _parse_model_id(model_id: str, known_families: list) -> tuple:
    """從 model_id 解析出 (family, variant)，依最長 family 前綴匹配"""
    for family in sorted(known_families, key=len, reverse=True):
        prefix = family + "-"
        if model_id.startswith(prefix):
            variant = model_id[len(prefix):]
            return family, variant
    raise ValueError(f"Unknown model_id: {model_id}. Known families: {known_families}")


class ImageUpscaleService:
    _instance: Optional["ImageUpscaleService"] = None

    def __new__(cls):
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
            TASK_TYPE_IMAGE_UPSCALE,
            self._handle_upscale_task,
        )

        self._initialized = True
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
        output_dir: Optional[str] = None,
    ) -> str:
        file_info = self._file_service.get_file(file_id)
        if not file_info:
            raise ValueError(f"File not found: {file_id}")

        task_id = await self._task_manager.submit(TASK_TYPE_IMAGE_UPSCALE, {
            "file_id": file_id,
            "model_id": model_id,
            "scale": scale,
            "sharpen": sharpen,
            "face_fix": face_fix,
            "face_restore_model_id": face_restore_model_id,
            "face_restore_fidelity": face_restore_fidelity,
            "face_restore_upscale": face_restore_upscale,
            "output_dir": output_dir,
        })
        return task_id

    def _handle_upscale_task(self, params: dict, progress_callback: Callable) -> dict:
        file_id  = params["file_id"]
        model_id = params["model_id"]
        scale    = params["scale"]
        face_fix = params.get("face_fix", False)
        face_restore_model_id = params.get("face_restore_model_id")

        file_info = self._file_service.get_file(file_id)

        # ── 超解析 ──────────────────────────────────────────
        upscale_family, upscale_variant = _parse_model_id(model_id, _UPSCALE_FAMILIES)
        progress_callback(0.05, f"正在載入模型: {model_id}...")

        from backend.core.ai.upscale import get_upscaler
        upscaler = get_upscaler(upscale_family)

        # 查詢模型的原生 scale
        from backend.core.ai.registry import MODELS_REGISTRY, FORMAT_PTH
        native_scale = MODELS_REGISTRY.get(FORMAT_PTH, {}).get(upscale_family, {}).get(
            "variants", {}
        ).get(upscale_variant, {}).get("scale", 4)

        with Image.open(file_info.file_path) as img:
            img = img.copy()

        upscale_end = 0.7 if face_fix else 0.85

        # 載入階段佔 5-40%；p=1.0 時改顯示「推理中」訊息
        result_img = upscaler.enhance(
            img,
            model_id=upscale_variant,
            scale=native_scale,
            on_progress=lambda p, m: progress_callback(
                0.05 + p * 0.35 if p <= 1.0 else 0.40 + (p - 1.0) * 0.30,
                m,
            ),
        )

        # 若使用者要求的倍率小於模型原生倍率，LANCZOS 縮到目標尺寸
        if scale < native_scale:
            orig_w, orig_h = img.size
            result_img = result_img.resize((orig_w * scale, orig_h * scale), Image.LANCZOS)

        # inference 完成後跳至目標進度
        progress_callback(upscale_end, "超解析完成")

        # ── 人臉修復（可選）──────────────────────────────────
        if face_fix and face_restore_model_id:
            try:
                face_family, face_variant = _parse_model_id(face_restore_model_id, _FACE_FAMILIES)
                fidelity = params.get("face_restore_fidelity", 0.7)
                face_upscale = params.get("face_restore_upscale", 2)
                progress_callback(0.75, f"正在載入人臉修復模型: {face_restore_model_id}...")

                from backend.core.ai.face_restore import get_face_restorer
                restorer = get_face_restorer(face_family)

                restore_kwargs: dict = {"model_id": face_variant, "on_progress": lambda p, m: progress_callback(0.75 + p * 0.15, m)}
                if face_family == "codeformer":
                    restore_kwargs["fidelity"] = fidelity
                elif face_family == "gfpgan":
                    restore_kwargs["upscale"] = face_upscale

                result_img = restorer.restore(result_img, **restore_kwargs)
            except Exception as e:
                logger.warning(f"Face restore failed, returning upscaled image only: {e}")

        output_file_id = str(uuid4())
        output_path = self._generate_output_path(file_info, scale, params.get("output_dir"))
        result_img.save(output_path, "PNG")

        progress_callback(0.95, "正在註冊結果...")
        output_info = self._file_service.register_output(
            file_id=output_file_id,
            file_path=output_path,
            original_filename=file_info.original_filename,
        )

        return {
            "output_file_id": output_file_id,
            "output_filename": output_info.filename,
            "scale": scale,
        }

    def _generate_output_path(self, file_info, scale, custom_dir) -> Path:
        target_dir = Path(custom_dir) if custom_dir else self._file_service.output_dir
        target_dir.mkdir(parents=True, exist_ok=True)
        return target_dir / f"{Path(file_info.original_filename).stem}_x{scale}_{uuid4().hex[:8]}.png"


def get_image_upscale_service() -> ImageUpscaleService:
    return ImageUpscaleService()
