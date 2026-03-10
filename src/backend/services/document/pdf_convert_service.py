"""
PDF / 文件轉換服務
支援：PDF → TXT / Markdown / Images(zip)
      DOCX → TXT / Markdown
"""
import io
import logging
import zipfile
from pathlib import Path
from typing import Callable, Optional
from uuid import uuid4

from backend.services.files.file_service import FileService, get_file_service
from backend.workers.task_manager import TaskManager, get_task_manager

logger = logging.getLogger(__name__)

TASK_TYPE = "document.pdf_convert"


class DocumentPdfConvertService:
    _instance: Optional["DocumentPdfConvertService"] = None

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
        self._task_manager.register_handler(TASK_TYPE, self._handle_task)
        self._initialized = True
        logger.info("DocumentPdfConvertService initialized")

    async def submit(
        self,
        file_id: str,
        output_format: str = "txt",
        output_dir: Optional[str] = None,
        output_filename: Optional[str] = None,
    ) -> str:
        file_info = self._file_service.get_file(file_id)
        if file_info is None:
            raise ValueError(f"File not found: {file_id}")
        params = {
            "file_id": file_id,
            "output_format": output_format,
            "output_dir": output_dir,
            "output_filename": output_filename,
        }
        return await self._task_manager.submit(TASK_TYPE, params)

    def _handle_task(self, params: dict, progress_callback: Callable[[float, str], None]) -> dict:
        file_id = params["file_id"]
        file_info = self._file_service.get_file(file_id)
        if file_info is None:
            raise ValueError(f"File not found: {file_id}")

        src_path = file_info.file_path
        src_ext = Path(file_info.original_filename).suffix.lower()
        output_format = params.get("output_format", "txt")
        output_file_id = str(uuid4())
        stem = Path(file_info.original_filename).stem

        ext_map = {"txt": "txt", "md": "md", "images": "zip"}
        ext = ext_map.get(output_format, "txt")

        custom_filename = params.get("output_filename")
        final_filename = custom_filename if custom_filename else f"{stem}_converted.{ext}"

        custom_output_dir = params.get("output_dir")
        if custom_output_dir:
            output_dir_path = Path(custom_output_dir)
        elif file_info.source_dir:
            output_dir_path = Path(file_info.source_dir)
        else:
            output_dir_path = self._file_service.output_dir
        output_dir_path.mkdir(parents=True, exist_ok=True)
        output_path = output_dir_path / final_filename

        progress_callback(0.05, "讀取文件...")

        if output_format == "images":
            if src_ext != ".pdf":
                raise ValueError("僅 PDF 格式支援轉換為圖片")
            self._pdf_to_images(src_path, output_path, progress_callback)
        elif src_ext == ".pdf":
            text = self._extract_pdf_text(src_path, progress_callback)
            content = self._maybe_to_md(text) if output_format == "md" else text
            output_path.write_text(content, encoding="utf-8")
        elif src_ext in (".docx", ".doc"):
            text = self._extract_docx_text(src_path, progress_callback)
            content = self._maybe_to_md(text) if output_format == "md" else text
            output_path.write_text(content, encoding="utf-8")
        else:
            # 純文字類檔案直接複製
            content = src_path.read_text(encoding="utf-8", errors="replace")
            output_path.write_text(content, encoding="utf-8")

        output_info = self._file_service.register_output(
            file_id=output_file_id,
            file_path=output_path,
            original_filename=final_filename,
        )

        progress_callback(1.0, "轉換完成")
        return {
            "output_file_id": output_file_id,
            "output_filename": output_info.filename,
        }

    def _extract_pdf_text(self, path: Path, progress_callback) -> str:
        import fitz  # pymupdf
        doc = fitz.open(str(path))
        parts = []
        total = len(doc)
        for i, page in enumerate(doc):
            parts.append(page.get_text())
            progress_callback(0.1 + (i + 1) / total * 0.8, f"提取頁面 {i+1}/{total}...")
        doc.close()
        return "\n\n".join(p.strip() for p in parts if p.strip())

    def _extract_docx_text(self, path: Path, progress_callback) -> str:
        import docx
        doc = docx.Document(str(path))
        lines = [p.text for p in doc.paragraphs if p.text.strip()]
        progress_callback(0.9, "提取文字完成")
        return "\n".join(lines)

    def _maybe_to_md(self, text: str) -> str:
        return text  # 純文字已夠可讀，直接回傳

    def _pdf_to_images(self, src_path: Path, output_path: Path, progress_callback):
        import fitz
        doc = fitz.open(str(src_path))
        total = len(doc)
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for i, page in enumerate(doc):
                mat = fitz.Matrix(2.0, 2.0)
                pix = page.get_pixmap(matrix=mat)
                zf.writestr(f"page_{i + 1:03d}.png", pix.tobytes("png"))
                progress_callback(0.1 + (i + 1) / total * 0.85, f"渲染頁面 {i+1}/{total}...")
        doc.close()
        output_path.write_bytes(buf.getvalue())


_service: Optional[DocumentPdfConvertService] = None


def get_pdf_convert_service() -> DocumentPdfConvertService:
    global _service
    if _service is None:
        _service = DocumentPdfConvertService()
    return _service
