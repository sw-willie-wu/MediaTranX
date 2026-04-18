"""File upload endpoint."""
from __future__ import annotations
from typing import Optional, TYPE_CHECKING

from dependency_injector.wiring import inject, Provide
from fastapi import APIRouter, Depends, File, Form, UploadFile
from pydantic import BaseModel

from app.init.container import AppContainer

if TYPE_CHECKING:
    from app.services.files.file_service import FileService


class FileUploadResponse(BaseModel):
    """File upload response."""
    file_id: str
    filename: str
    file_size: int
    mime_type: str


router = APIRouter()


@router.post("/upload", response_model=FileUploadResponse)
@inject
async def upload_file(
    file: UploadFile = File(...),
    source_dir: Optional[str] = Form(default=None),
    file_service: FileService = Depends(Provide[AppContainer.file_service]),
):
    """
    Upload a file.

    Args:
        file: The uploaded file
        source_dir: Original directory on the user's machine (provided by Electron)

    Returns:
        FileUploadResponse containing the file_id.
    """
    content = await file.read()
    file_data = await file_service.save_upload(
        filename=file.filename or "unnamed",
        content=content,
        mime_type=file.content_type,
        source_dir=source_dir
    )

    return FileUploadResponse(
        file_id=file_data.file_id,
        filename=file_data.original_filename,
        file_size=file_data.file_size,
        mime_type=file_data.mime_type
    )
