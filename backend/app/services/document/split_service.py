"""PDF split service: extract pages by range into a new PDF."""
import logging
from pathlib import Path
from typing import Callable
from uuid import uuid4

from app.services.files.file_service import FileService
from app.workers.task_manager import TaskManager

logger = logging.getLogger(__name__)

TASK_TYPE_DOCUMENT_SPLIT = "document.split"


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
    """PDF page extraction and splitting service."""

    def __init__(self, file_service: FileService, task_manager: TaskManager):
        self._file_service = file_service
        self._task_manager = task_manager
        self._task_manager.register_handler(
            TASK_TYPE_DOCUMENT_SPLIT, self._handle_task,
            output_policy="results",
        )
        logger.info("DocumentSplitService initialized")

    async def submit(
        self,
        file_id: str,
        pages: str,
    ) -> str:
        file_info = self._file_service.require_file(file_id)
        params = {
            "file_id": file_id, "pages": pages,
        }
        task_id = await self._task_manager.submit(TASK_TYPE_DOCUMENT_SPLIT, params)
        logger.info(f"Document split task submitted: {task_id}")
        return task_id

    def _handle_task(self, params: dict, progress_callback: Callable[[float, str], None]) -> dict:
        return self._execute(params, progress_callback)

    def _execute(self, params: dict, progress_callback: Callable[[float, str], None]) -> dict:
        from pypdf import PdfReader, PdfWriter

        file_id = params["file_id"]
        file_info = self._file_service.require_file(file_id)

        progress_callback(0.1, "task.progress.reading_pdf")
        reader = PdfReader(str(file_info.file_path))
        total = len(reader.pages)

        pages_str = params.get("pages", "").strip()
        page_indices = _parse_page_ranges(pages_str, total) if pages_str else list(range(total))
        if not page_indices:
            raise ValueError("Invalid page range")

        writer = PdfWriter()
        for idx in page_indices:
            writer.add_page(reader.pages[idx])

        progress_callback(0.8, "task.progress.writing_output")
        output_file_id = str(uuid4())
        stem = Path(file_info.original_filename).stem
        label = pages_str.replace(" ", "").replace(",", "_") if pages_str else "all"
        final_filename = f"{stem}_p{label}.pdf"

        output_dir = self._file_service.output_dir
        output_path = output_dir / final_filename

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
