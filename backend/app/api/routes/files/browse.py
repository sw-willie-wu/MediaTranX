"""File browse endpoints: list, stats, get-info.

Note: `list_files` (GET "") is registered on the aggregator router in this
package's `__init__.py` — FastAPI refuses an empty prefix + empty path
combination when including a sub-router. Stats + get-info live here under
this module's own router.
"""
from __future__ import annotations
from datetime import datetime
from typing import Literal, Optional, TYPE_CHECKING

from dependency_injector.wiring import inject, Provide
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, field_serializer

from app.init.container import AppContainer
from app.schemas.file import FileData

if TYPE_CHECKING:
    from app.services.files.file_service import FileService


def _serialize_dt(v: datetime) -> str:
    return v.isoformat()


class FileInfo(BaseModel):
    """File API response model."""
    file_id: str
    filename: str
    original_filename: str
    file_path: str
    file_size: int
    mime_type: str
    source_dir: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    metadata: Optional[dict] = None

    _serialize_created_at = field_serializer("created_at")(_serialize_dt)

    @classmethod
    def from_file_data(cls, f: FileData) -> "FileInfo":
        return cls(
            file_id=f.file_id,
            filename=f.filename,
            original_filename=f.original_filename,
            file_path=f.file_path,
            file_size=f.file_size,
            mime_type=f.mime_type,
            source_dir=f.source_dir,
            created_at=f.created_at,
            metadata=f.metadata,
        )


class TempStats(BaseModel):
    """Temp folder byte usage response model."""
    upload_bytes: int
    output_bytes: int
    total_bytes: int


router = APIRouter()


@inject
async def list_files(
    kind: Optional[Literal["output"]] = None,
    file_service: "FileService" = Depends(Provide[AppContainer.file_service]),
):
    """List registered files.

    - `kind=output`: return files with metadata.show_in_results=True
      (Results drawer init).
    - omit kind: return all registered files (debug / admin).
    """
    if kind == "output":
        return [FileInfo.from_file_data(f) for f in file_service.get_output_files()]
    return [FileInfo.from_file_data(f) for f in file_service.list_files()]


@router.get("/stats", response_model=TempStats)
@inject
async def get_stats(
    file_service: FileService = Depends(Provide[AppContainer.file_service]),
):
    """Return temp folder byte usage for Settings display."""
    return TempStats(**file_service.get_temp_stats())


@router.get("/{file_id}", response_model=FileInfo)
@inject
async def get_file_info(
    file_id: str,
    file_service: FileService = Depends(Provide[AppContainer.file_service]),
):
    """
    Get file information.

    Args:
        file_id: File ID
    """
    return FileInfo.from_file_data(file_service.require_file(file_id))
