"""File download endpoint."""
from __future__ import annotations
from pathlib import Path
from typing import TYPE_CHECKING

from dependency_injector.wiring import inject, Provide
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from app.init.container import AppContainer

if TYPE_CHECKING:
    from app.services.files.file_service import FileService


router = APIRouter()


@router.get("/{file_id}/download")
@inject
async def download_file(
    file_id: str,
    file_service: FileService = Depends(Provide[AppContainer.file_service]),
):
    """
    Download a file.

    Args:
        file_id: File ID
    """
    file_data = file_service.get_file(file_id)

    if file_data is None:
        raise HTTPException(status_code=404, detail="File not found")

    file_path = Path(file_data.file_path)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found on disk")

    return FileResponse(
        path=file_path,
        filename=file_data.original_filename,
        media_type=file_data.mime_type
    )
