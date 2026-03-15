"""
文件 OCR 服務
PDF：逐頁渲染後以 VLM 辨識；圖片：直接辨識
"""
import logging
import os
import tempfile
from pathlib import Path
from typing import Callable, Optional
from uuid import uuid4

from app.engine.ai.llama.vlm import get_vlm_ocr, DEFAULT_VLM_MODEL
from app.services.files.file_service import FileService, get_file_service
from app.workers.task_manager import TaskManager, get_task_manager

logger = logging.getLogger(__name__)

TASK_TYPE = "document.ocr"

_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tiff", ".tif"}


class DocumentOcrService:
    _instance: Optional["DocumentOcrService"] = None

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
        self._task_manager.register_handler(TASK_TYPE, self._handle_task)
        self._initialized = True
        logger.info("DocumentOcrService initialized")

    def get_status(self, model_id: str = DEFAULT_VLM_MODEL, size: str = "4b",
                   quantization: Optional[str] = None) -> dict:
        return self._ocr.get_status(model_id=model_id, size=size, quantization=quantization)

    async def submit(
        self,
        file_id: str,
        model_id: str = DEFAULT_VLM_MODEL,
        size: str = "4b",
        quantization: Optional[str] = None,
        format: str = "md",
        output_dir: Optional[str] = None,
        output_filename: Optional[str] = None,
    ) -> str:
        file_info = self._file_service.get_file(file_id)
        if file_info is None:
            raise ValueError(f"File not found: {file_id}")
        params = {
            "file_id": file_id, "model_id": model_id,
            "size": size, "quantization": quantization,
            "format": format, "output_dir": output_dir,
            "output_filename": output_filename,
        }
        return await self._task_manager.submit(TASK_TYPE, params)

    def _handle_task(self, params: dict, progress_callback: Callable[[float, str], None]) -> dict:
        file_id = params["file_id"]
        file_info = self._file_service.get_file(file_id)
        if file_info is None:
            raise ValueError(f"File not found: {file_id}")

        if not self._ocr.is_available():
            raise RuntimeError("llama-server 未安裝，請先至設定頁面安裝 AI 核心環境")

        model_id = params.get("model_id", DEFAULT_VLM_MODEL)
        size = params.get("size", "4b")
        quantization = params.get("quantization")
        fmt = params.get("format", "md")
        ext = "md" if fmt == "md" else "txt"
        src_ext = Path(file_info.original_filename).suffix.lower()

        progress_callback(0.05, "準備辨識...")

        if src_ext == ".pdf":
            final_text = self._ocr_pdf(
                file_info.file_path, model_id, size, quantization, fmt, progress_callback,
            )
        elif src_ext in _IMAGE_EXTS:
            final_text = self._ocr.recognize(
                image_path=str(file_info.file_path),
                model_id=model_id, size=size, quantization=quantization, format=fmt,
                on_progress=lambda p, m: progress_callback(0.1 + p * 0.85, m),
            )
        else:
            raise ValueError("不支援的檔案格式，請上傳 PDF 或圖片")

        if not final_text.strip():
            final_text = "(未偵測到文字)"

        output_file_id = str(uuid4())
        stem = Path(file_info.original_filename).stem
        custom_filename = params.get("output_filename")
        final_filename = custom_filename if custom_filename else f"{stem}_ocr_{output_file_id[:8]}.{ext}"

        custom_output_dir = params.get("output_dir")
        if custom_output_dir:
            out_dir = Path(custom_output_dir)
        elif file_info.source_dir:
            out_dir = Path(file_info.source_dir)
        else:
            out_dir = self._file_service.output_dir
        out_dir.mkdir(parents=True, exist_ok=True)
        output_path = out_dir / final_filename
        output_path.write_text(final_text, encoding="utf-8")

        output_info = self._file_service.register_output(
            file_id=output_file_id, file_path=output_path,
            original_filename=final_filename,
        )
        progress_callback(1.0, "OCR 完成")
        return {
            "output_file_id": output_file_id,
            "output_filename": output_info.filename,
            "char_count": len(final_text),
        }

    def _ocr_pdf(self, src_path: Path, model_id, size, quantization, fmt, progress_callback) -> str:
        import io as _io
        import pypdfium2
        doc = pypdfium2.PdfDocument(str(src_path))
        total = len(doc)
        page_results = []

        for i, page in enumerate(doc):
            progress_callback(0.1 + i / total * 0.85, f"辨識頁面 {i+1}/{total}...")
            bitmap = page.render(scale=2.0)
            img = bitmap.to_pil()
            img_buf = _io.BytesIO()
            img.save(img_buf, format="PNG")
            img_bytes = img_buf.getvalue()

            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
                tmp.write(img_bytes)
                tmp_path = tmp.name
            try:
                text = self._ocr.recognize(
                    image_path=tmp_path,
                    model_id=model_id, size=size, quantization=quantization,
                    format=fmt, on_progress=lambda p, m: None,
                )
                page_results.append(text.strip())
            finally:
                os.unlink(tmp_path)

        doc.close()

        if fmt == "md":
            parts = []
            for i, text in enumerate(page_results):
                header = f"## 第 {i+1} 頁\n\n" if total > 1 else ""
                parts.append(f"{header}{text}")
            return "\n\n---\n\n".join(parts)
        return "\n\n".join(page_results)


_service: Optional[DocumentOcrService] = None


def get_doc_ocr_service() -> DocumentOcrService:
    global _service
    if _service is None:
        _service = DocumentOcrService()
    return _service
