"""
圖片 OCR 服務
使用視覺語言模型（Qwen3-VL / InternVL2.5 / Gemma3）辨識圖片中的文字。
"""
import logging
from pathlib import Path
from typing import Callable, Optional
from uuid import uuid4

from app.utils.prompts import DEFAULT_VLM_MODEL, build_ocr_messages, OCR_PARAMS
from app.services.files.file_service import FileService, get_file_service
from app.workers.task_manager import TaskManager, get_task_manager

logger = logging.getLogger(__name__)

TASK_TYPE_IMAGE_OCR = "image.ocr"
TASK_TYPE_IMAGE_OCR_REMOTE = "image.ocr.remote"


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
        self._file_service: FileService = get_file_service()
        self._task_manager: TaskManager = get_task_manager()
        self._task_manager.register_handler(TASK_TYPE_IMAGE_OCR, self._handle_task)
        self._task_manager.register_handler(TASK_TYPE_IMAGE_OCR_REMOTE, self._handle_remote_task)
        self._initialized = True
        logger.info("ImageOcrService initialized")

    def get_status(
        self,
        model_id: str = DEFAULT_VLM_MODEL,
        size: str = "4b",
        quantization: Optional[str] = None,
    ) -> dict:
        """查詢 VLM OCR 狀態"""
        from app.services.setup.language_service import get_language_service
        return get_language_service().get_vlm_status(model_id=model_id, size=size, quantization=quantization)

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

        from app.engine.ai.model_manager import get_model_manager
        if not get_model_manager().is_llama_ready():
            raise RuntimeError("llama-server 未安裝，請先至設定頁面安裝 AI 核心環境")

        # === GPU 排隊管線 ===
        manager = get_model_manager()

        with manager.gpu_session():
            # 執行 VLM OCR
            from app.engine.ai.runtime.llama_server import LlamaServerRuntime
            from app.engine.ai.registry import SLOT_VLM

            variant = f"{size}:{quantization}" if quantization else size
            runtime = LlamaServerRuntime(SLOT_VLM)
            messages = build_ocr_messages(str(file_info.file_path), format=fmt)

            with runtime.acquire(model_id, variant, lambda p, m: progress_callback(0.1 + p * 0.85, m)):
                final_text = runtime.chat(messages=messages, max_tokens=4096, temperature=0.0)

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


    async def submit_ocr_remote(
        self,
        file_id: str,
        provider: str,
        conn_id: Optional[int],
        remote_model: str,
        format: str = "md",
        output_dir: Optional[str] = None,
        output_filename: Optional[str] = None,
    ) -> str:
        """提交雲端 OCR 任務"""
        file_info = self._file_service.get_file(file_id)
        if file_info is None:
            raise ValueError(f"File not found: {file_id}")

        params = {
            "file_id": file_id,
            "provider": provider,
            "conn_id": conn_id,
            "remote_model": remote_model,
            "format": format,
            "output_dir": output_dir,
            "output_filename": output_filename,
        }
        task_id = await self._task_manager.submit(TASK_TYPE_IMAGE_OCR_REMOTE, params)
        logger.info(f"Remote OCR task submitted: {task_id} (provider={provider}, model={remote_model})")
        return task_id

    def _handle_remote_task(self, params: dict, progress_callback: Callable[[float, str], None]) -> dict:
        """處理雲端 OCR 任務"""
        import base64

        file_id = params["file_id"]
        file_info = self._file_service.get_file(file_id)
        if file_info is None:
            raise ValueError(f"File not found: {file_id}")

        provider = params["provider"]
        conn_id = params.get("conn_id")
        remote_model = params["remote_model"]
        fmt = params.get("format", "md")
        ext = "md" if fmt == "md" else "txt"

        progress_callback(0.05, f"連接 {provider}...")

        # 取得連線資訊
        from app.services.setup.remote_service import get_remote_service
        remote_svc = get_remote_service()
        p = remote_svc.get_provider_for_connection(conn_id, provider)
        if p is None:
            raise RuntimeError(f"Provider not available: {provider}")

        # 讀取圖片，必要時壓縮（API 通常有 ~20MB payload 限制）
        progress_callback(0.1, "準備圖片...")
        image_path = Path(file_info.file_path)

        MAX_SIZE_BYTES = 4 * 1024 * 1024  # 4MB（base64 後約 5.3MB）
        MAX_DIMENSION = 2048

        from PIL import Image as PILImage
        import io

        img = PILImage.open(image_path)
        original_size = image_path.stat().st_size

        # 縮放大圖
        if max(img.size) > MAX_DIMENSION:
            img.thumbnail((MAX_DIMENSION, MAX_DIMENSION), PILImage.LANCZOS)
            logger.info(f"Image resized to {img.size} for remote OCR")

        # 轉 JPEG 壓縮（如果原圖太大或是 PNG/BMP）
        buf = io.BytesIO()
        if original_size > MAX_SIZE_BYTES or image_path.suffix.lower() in ('.png', '.bmp', '.tiff'):
            img_rgb = img.convert('RGB') if img.mode != 'RGB' else img
            img_rgb.save(buf, format='JPEG', quality=85, optimize=True)
            mime_type = "image/jpeg"
        else:
            img.save(buf, format=img.format or 'JPEG')
            suffix = image_path.suffix.lower()
            mime_map = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".gif": "image/gif", ".webp": "image/webp"}
            mime_type = mime_map.get(suffix, "image/jpeg")

        image_b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
        logger.info(f"Image prepared: {len(buf.getvalue()) / 1024:.0f}KB (base64: {len(image_b64) / 1024:.0f}KB)")

        # 組裝 prompt
        if fmt == "md":
            prompt = "Please perform OCR on this image. Extract all text content and format it as clean Markdown. Preserve the document structure (headings, lists, tables, etc.) as much as possible. Output only the extracted text in Markdown format, no explanations."
        else:
            prompt = "Please perform OCR on this image. Extract all text content as plain text. Output only the extracted text, no explanations."

        progress_callback(0.2, "辨識中...")

        # 依 provider 組裝 vision messages（格式不同）
        if provider == "ollama":
            # Ollama: images 欄位放 base64（不含 data: prefix）
            messages = [{"role": "user", "content": prompt, "images": [image_b64]}]
        elif provider == "gemini":
            # Gemini: inline_data 格式
            messages = [{"role": "user", "content": [
                {"type": "text", "text": prompt},
                {"type": "image", "mime_type": mime_type, "data": image_b64},
            ]}]
        else:
            # OpenAI-compatible: image_url with data URI
            messages = [{"role": "user", "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{image_b64}"}},
            ]}]

        final_text = p.chat(model=remote_model, messages=messages, max_tokens=4096, temperature=0.1)

        if not final_text.strip():
            final_text = "(未偵測到文字)"

        # 儲存結果
        progress_callback(0.95, "儲存結果...")
        output_file_id = str(uuid4())
        original_stem = Path(file_info.original_filename).stem
        custom_filename = params.get("output_filename")
        final_filename = custom_filename if custom_filename else f"{original_stem}_ocr_{output_file_id[:8]}.{ext}"

        custom_output_dir = params.get("output_dir")
        if custom_output_dir:
            output_dir_path = Path(custom_output_dir)
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
