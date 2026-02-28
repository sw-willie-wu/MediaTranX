"""
圖片超解析服務（Real-ESRGAN / waifu2x ncnn-vulkan）
"""
import logging
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Callable, Optional
from uuid import uuid4

from PIL import Image, ImageFilter

from backend.core.paths import get_realesrgan_dir, get_waifu2x_dir
from backend.services.files.file_service import FileService, get_file_service
from backend.workers.task_manager import TaskManager, get_task_manager

logger = logging.getLogger(__name__)

TASK_TYPE_IMAGE_UPSCALE = "image.upscale"

# Real-ESRGAN 模型對應
REALESRGAN_MODEL_MAP = {
    "photo": "realesrgan-x4plus",
    "anime": "realesrgan-x4plus-anime",
}

# waifu2x 模型目錄對應（相對 bin/waifu2x/）
WAIFU2X_MODEL_MAP = {
    "photo": "models-upconv_7_photo",
    "anime": "models-cunet",
}


class ImageUpscaleService:
    _instance: Optional["ImageUpscaleService"] = None

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
            TASK_TYPE_IMAGE_UPSCALE,
            self._handle_upscale_task
        )
        self._initialized = True
        logger.info("ImageUpscaleService initialized")

    # ── 路徑 ──────────────────────────────────────────────────────────

    def get_realesrgan_exe(self) -> Path:
        return get_realesrgan_dir() / "realesrgan-ncnn-vulkan.exe"

    def get_waifu2x_exe(self) -> Path:
        return get_waifu2x_dir() / "waifu2x-ncnn-vulkan.exe"

    def is_realesrgan_available(self) -> bool:
        return self.get_realesrgan_exe().exists()

    def is_waifu2x_available(self) -> bool:
        return self.get_waifu2x_exe().exists()

    # ── 提交 ──────────────────────────────────────────────────────────

    async def submit_upscale(
        self,
        file_id: str,
        scale: int = 4,
        model: str = "photo",
        engine: str = "realesrgan",
        sharpen: bool = False,
        output_dir: Optional[str] = None,
        output_filename: Optional[str] = None,
    ) -> str:
        file_info = self._file_service.get_file(file_id)
        if file_info is None:
            raise ValueError(f"File not found: {file_id}")

        if engine == "realesrgan" and not self.is_realesrgan_available():
            raise RuntimeError("Real-ESRGAN binary not found")
        if engine == "waifu2x" and not self.is_waifu2x_available():
            raise RuntimeError("waifu2x binary not found")

        if model not in REALESRGAN_MODEL_MAP:
            raise ValueError(f"Unknown model: {model}")
        if scale not in (2, 3, 4):
            raise ValueError(f"Invalid scale: {scale}")

        params = {
            "file_id": file_id,
            "scale": scale,
            "model": model,
            "engine": engine,
            "sharpen": sharpen,
            "output_dir": output_dir,
            "output_filename": output_filename,
        }
        task_id = await self._task_manager.submit(TASK_TYPE_IMAGE_UPSCALE, params)
        logger.info(f"Upscale task submitted: {task_id} engine={engine}")
        return task_id

    # ── 執行 ──────────────────────────────────────────────────────────

    def _handle_upscale_task(self, params: dict, progress_callback: Callable) -> dict:
        return self._execute_upscale(params, progress_callback)

    def _execute_upscale(self, params: dict, progress_callback: Callable) -> dict:
        file_id = params["file_id"]
        file_info = self._file_service.get_file(file_id)
        if file_info is None:
            raise ValueError(f"File not found: {file_id}")

        scale = params.get("scale", 4)
        model = params.get("model", "photo")
        engine = params.get("engine", "realesrgan")
        sharpen = params.get("sharpen", False)

        progress_callback(0.05, "準備超解析...")

        # 建立輸出路徑
        output_file_id = str(uuid4())
        original_stem = Path(file_info.original_filename).stem
        custom_output_filename = params.get("output_filename")
        if custom_output_filename:
            final_filename = f"{Path(custom_output_filename).stem}.png"
        else:
            final_filename = f"{original_stem}_x{scale}_{output_file_id[:8]}.png"

        custom_output_dir = params.get("output_dir")
        if custom_output_dir:
            output_dir_path = Path(custom_output_dir)
        elif file_info.source_dir:
            output_dir_path = Path(file_info.source_dir)
        else:
            output_dir_path = self._file_service.output_dir
        output_dir_path.mkdir(parents=True, exist_ok=True)
        output_path = output_dir_path / final_filename

        # 執行對應引擎
        if engine == "waifu2x":
            self._run_waifu2x(file_info.file_path, output_path, scale, model, progress_callback)
        else:
            self._run_realesrgan(file_info.file_path, output_path, scale, model, progress_callback)

        # 銳化後處理
        if sharpen and output_path.exists():
            progress_callback(0.92, "套用銳化後處理...")
            self._apply_sharpen(output_path)

        if not output_path.exists():
            raise RuntimeError("超解析執行完畢但找不到輸出檔案")

        progress_callback(0.95, "註冊輸出檔案...")
        output_info = self._file_service.register_output(
            file_id=output_file_id,
            file_path=output_path,
            original_filename=file_info.original_filename,
        )
        progress_callback(1.0, "超解析完成")

        return {
            "output_file_id": output_file_id,
            "output_filename": output_info.filename,
            "output_size": output_info.file_size,
            "scale": scale,
        }

    # ── Real-ESRGAN ────────────────────────────────────────────────────

    def _run_realesrgan(
        self, input_path: Path, output_path: Path, scale: int, model: str,
        progress_callback: Callable
    ):
        exe = self.get_realesrgan_exe()
        models_dir = get_realesrgan_dir() / "models"
        model_name = REALESRGAN_MODEL_MAP[model]

        cmd = [
            str(exe),
            "-i", str(input_path),
            "-o", str(output_path),
            "-s", str(scale),
            "-n", model_name,
            "-m", str(models_dir),
        ]
        logger.info(f"Real-ESRGAN: {' '.join(cmd)}")
        progress_callback(0.1, f"Real-ESRGAN 超解析 {scale}x...")
        self._run_cmd(cmd, "Real-ESRGAN")

    # ── waifu2x ───────────────────────────────────────────────────────

    def _run_waifu2x(
        self, input_path: Path, output_path: Path, scale: int, model: str,
        progress_callback: Callable
    ):
        """
        waifu2x 原生只支援 2x。
        - 2x: 直接跑一次
        - 4x: 跑兩次（2x → 2x）
        - 3x: 跑一次 2x，再用 PIL resize 到 3x
        """
        exe = self.get_waifu2x_exe()
        model_dir = get_waifu2x_dir() / WAIFU2X_MODEL_MAP[model]
        noise = 2  # noise level 0-3，2 是預設推薦值

        progress_callback(0.1, f"waifu2x 超解析...")

        if scale == 2:
            self._waifu2x_pass(exe, model_dir, noise, input_path, output_path)

        elif scale == 4:
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
                tmp_path = Path(tmp.name)
            try:
                progress_callback(0.15, "waifu2x 第一次 2x...")
                self._waifu2x_pass(exe, model_dir, noise, input_path, tmp_path)
                progress_callback(0.55, "waifu2x 第二次 2x...")
                self._waifu2x_pass(exe, model_dir, noise, tmp_path, output_path)
            finally:
                tmp_path.unlink(missing_ok=True)

        elif scale == 3:
            # 2x 後用 PIL 縮到 3x
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
                tmp_path = Path(tmp.name)
            try:
                progress_callback(0.15, "waifu2x 2x 中...")
                self._waifu2x_pass(exe, model_dir, noise, input_path, tmp_path)
                progress_callback(0.75, "調整至 3x...")
                with Image.open(tmp_path) as img:
                    orig_w = img.width // 2
                    orig_h = img.height // 2
                    new_w = orig_w * 3
                    new_h = orig_h * 3
                    img.resize((new_w, new_h), Image.Resampling.LANCZOS).save(str(output_path))
            finally:
                tmp_path.unlink(missing_ok=True)

    def _waifu2x_pass(
        self, exe: Path, model_dir: Path, noise: int,
        input_path: Path, output_path: Path
    ):
        cmd = [
            str(exe),
            "-i", str(input_path),
            "-o", str(output_path),
            "-s", "2",
            "-n", str(noise),
            "-m", str(model_dir),
        ]
        logger.info(f"waifu2x: {' '.join(cmd)}")
        self._run_cmd(cmd, "waifu2x")

    # ── 通用 ──────────────────────────────────────────────────────────

    def _run_cmd(self, cmd: list, name: str):
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        except subprocess.TimeoutExpired:
            raise RuntimeError(f"{name} 逾時（超過 5 分鐘）")
        if result.returncode != 0:
            err = result.stderr.strip() or result.stdout.strip()
            logger.error(f"{name} failed: {err}")
            raise RuntimeError(f"{name} 失敗: {err[:200]}")

    def _apply_sharpen(self, path: Path):
        """PIL UnsharpMask 銳化後處理"""
        try:
            with Image.open(path) as img:
                sharpened = img.filter(
                    ImageFilter.UnsharpMask(radius=1.5, percent=120, threshold=3)
                )
                sharpened.save(str(path))
        except Exception as e:
            logger.warning(f"Sharpen post-process failed: {e}")


_image_upscale_service: Optional[ImageUpscaleService] = None


def get_image_upscale_service() -> ImageUpscaleService:
    global _image_upscale_service
    if _image_upscale_service is None:
        _image_upscale_service = ImageUpscaleService()
    return _image_upscale_service
