"""
圖片 OCR 服務
使用視覺語言模型（Qwen3-VL / InternVL2.5 / Gemma3）辨識圖片中的文字。
"""
import logging
from pathlib import Path
from typing import Callable, Optional
from uuid import uuid4

from app.engine.ai.llama.vlm import get_vlm_ocr, DEFAULT_VLM_MODEL
from app.services.files.file_service import FileService, get_file_service
from app.workers.task_manager import TaskManager, get_task_manager

logger = logging.getLogger(__name__)

TASK_TYPE_IMAGE_OCR = "image.ocr"


class ImageOcrService:
    _instance: Optional["ImageOcrService"] = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._ocr = get_vlm_ocr()
        self._file_service: FileService = get_file_service()
        self._task_manager: TaskManager = get_task_manager()
        self._task_manager.register_handler(TASK_TYPE_IMAGE_OCR, self._handle_task)
        self._initialized = True
        logger.info("ImageOcrService initialized")

    def get_status(
        self,
        model_id: str = DEFAULT_VLM_MODEL,
        size: str = "4b",
        quantization: Optional[str] = None,
    ) -> dict:
        """查詢 VLM OCR 狀態"""
        return self._ocr.get_status(model_id=model_id, size=size, quantization=quantization)

    async def submit_ocr(
        self,
        file_id: str,
        model_id: str = DEFAULT_VLM_MODEL,
        size: str = "4b",
        quantization: Optional[str] = None,
        format: str = "md",
        output_dir: Optional[str] = None,
        output_filename: Optional[str] = None,
    ) -> str:
        """提交 OCR 任務"""
        file_info = self._file_service.get_file(file_id)
        if file_info is None:
            raise ValueError(f"File not found: {file_id}")

        params = {
            "file_id": file_id,
            "model_id": model_id,
            "size": size,
            "quantization": quantization,
            "format": format,
            "output_dir": output_dir,
            "output_filename": output_filename,
        }
        task_id = await self._task_manager.submit(TASK_TYPE_IMAGE_OCR, params)
        logger.info(f"Image OCR task submitted: {task_id}")
        return task_id

    def _handle_task(self, params: dict, progress_callback: Callable[[float, str], None]) -> dict:
        file_id = params["file_id"]
        file_info = self._file_service.get_file(file_id)
        if file_info is None:
            raise ValueError(f"File not found: {file_id}")

        model_id = params.get("model_id", DEFAULT_VLM_MODEL)
        size = params.get("size", "4b")
        quantization = params.get("quantization")
        fmt = params.get("format", "md")
        ext = "md" if fmt == "md" else "txt"

        progress_callback(0.05, "準備辨識...")

        if not self._ocr.is_available():
            raise RuntimeError("llama-server 未安裝，請先至設定頁面安裝 AI 核心環境")

        # 執行 VLM OCR
        final_text = self._ocr.recognize(
            image_path=str(file_info.file_path),
            model_id=model_id,
            size=size,
            quantization=quantization,
            format=fmt,
            on_progress=lambda p, m: progress_callback(0.1 + p * 0.85, m),
        )

        if not final_text.strip():
            final_text = "(未偵測到文字)"

        # 儲存輸出檔案
        progress_callback(0.97, "儲存結果...")
        output_file_id = str(uuid4())
        original_stem = Path(file_info.original_filename).stem
        custom_filename = params.get("output_filename")
        final_filename = custom_filename if custom_filename else f"{original_stem}_ocr_{output_file_id[:8]}.{ext}"

        custom_output_dir = params.get("output_dir")
        if custom_output_dir:
            output_dir_path = Path(custom_output_dir)
        elif file_info.source_dir:
            output_dir_path = Path(file_info.source_dir)
        else:
            output_dir_path = self._file_service.output_dir
        output_dir_path.mkdir(parents=True, exist_ok=True)
        output_path = output_dir_path / final_filename

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(final_text)

        output_info = self._file_service.register_output(
            file_id=output_file_id,
            file_path=output_path,
            original_filename=final_filename,
        )

        progress_callback(1.0, "OCR 完成")
        return {
            "output_file_id": output_file_id,
            "output_filename": output_info.filename,
            "char_count": len(final_text),
        }


_service: Optional[ImageOcrService] = None


def get_image_ocr_service() -> ImageOcrService:
    global _service
    if _service is None:
        _service = ImageOcrService()
    return _service
