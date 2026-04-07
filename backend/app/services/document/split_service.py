"""
PDF 分割服務：依頁碼範圍提取為新 PDF
"""
import logging
from pathlib import Path
from typing import Callable, Optional
from uuid import uuid4

from app.services.files.file_service import FileService
from app.workers.task_manager import TaskManager

logger = logging.getLogger(__name__)

TASK_TYPE = "document.split"


def _parse_page_ranges(s: str, total: int) -> list[int]:
    """'1-3,5,7-9' → [0,1,2,4,6,7,8] (0-indexed)"""
    pages: set[int] = set()
    for part in s.replace(" ", "").split(","):
        if not part:
            continue
        if "-" in part:
            a, b = part.split("-", 1)
            lo = max(1, int(a))
            hi = min(total, int(b))
            pages.update(range(lo - 1, hi))
        else:
            p = int(part)
            if 1 <= p <= total:
                pages.add(p - 1)
    return sorted(pages)


class DocumentSplitService:

    def __init__(self, file_service: FileService, task_manager: TaskManager):
        self._file_service = file_service
        self._task_manager = task_manager
        self._task_manager.register_handler(TASK_TYPE, self._handle_task)
        logger.info("DocumentSplitService initialized")

    async def submit(
        self,
        file_id: str,
        pages: str,
        output_dir: Optional[str] = None,
        output_filename: Optional[str] = None,
    ) -> str:
        file_info = self._file_service.get_file(file_id)
        if file_info is None:
            raise ValueError(f"File not found: {file_id}")
        params = {
            "file_id": file_id, "pages": pages,
            "output_dir": output_dir, "output_filename": output_filename,
        }
        return await self._task_manager.submit(TASK_TYPE, params)

    def _handle_task(self, params: dict, progress_callback: Callable[[float, str], None]) -> dict:
        from pypdf import PdfReader, PdfWriter

        file_id = params["file_id"]
        file_info = self._file_service.get_file(file_id)
        if file_info is None:
            raise ValueError(f"File not found: {file_id}")

        progress_callback(0.1, "task.progress.reading_pdf")
        reader = PdfReader(str(file_info.file_path))
        total = len(reader.pages)

        pages_str = params.get("pages", "").strip()
        page_indices = _parse_page_ranges(pages_str, total) if pages_str else list(range(total))
        if not page_indices:
            raise ValueError("頁碼範圍無效")

        writer = PdfWriter()
        for idx in page_indices:
            writer.add_page(reader.pages[idx])

        progress_callback(0.8, "task.progress.writing_output")
        output_file_id = str(uuid4())
        stem = Path(file_info.original_filename).stem
        label = pages_str.replace(" ", "").replace(",", "_") if pages_str else "all"
        custom_filename = params.get("output_filename")
        final_filename = custom_filename if custom_filename else f"{stem}_p{label}.pdf"

        custom_output_dir = params.get("output_dir")
        if custom_output_dir:
            out_dir = Path(custom_output_dir)
        else:
            out_dir = self._file_service.output_dir
        out_dir.mkdir(parents=True, exist_ok=True)
        output_path = out_dir / final_filename

        with open(output_path, "wb") as f:
            writer.write(f)

        output_info = self._file_service.register_output(
            file_id=output_file_id, file_path=output_path,
            original_filename=final_filename,
        )
        progress_callback(1.0, "task.progress.split_complete")
        return {
            "output_file_id": output_file_id,
            "output_filename": output_info.filename,
            "page_count": len(page_indices),
            "total_pages": total,
        }
