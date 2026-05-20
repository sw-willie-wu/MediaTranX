"""File download endpoint."""
from __future__ import annotations
from typing import TYPE_CHECKING

from dependency_injector.wiring import inject, Provide
from fastapi import APIRouter, Depends
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
    """Download a file."""
    file_data = file_service.require_file_on_disk(file_id)
    return FileResponse(
        path=file_data.file_path,
        filename=file_data.original_filename,
        media_type=file_data.mime_type,
    )
