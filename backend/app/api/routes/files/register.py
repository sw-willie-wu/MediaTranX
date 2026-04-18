"""File registration + saved-path endpoints."""
from __future__ import annotations
from pathlib import Path
from typing import TYPE_CHECKING

from dependency_injector.wiring import inject, Provide
from fastapi import APIRouter, Depends, HTTPException
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


class RegisterRequest(BaseModel):
    file_path: str


class SavedPathRequest(BaseModel):
    saved_path: str


router = APIRouter()


@router.post("/register", response_model=FileUploadResponse)
@inject
async def register_local_file(
    req: RegisterRequest,
    file_service: FileService = Depends(Provide[AppContainer.file_service]),
):
    """
    Register a local file (without copying); uses the original path directly.
    Designed for the Electron desktop environment to avoid copying large files.
    """
    file_data = file_service.register_local_file(req.file_path)

    return FileUploadResponse(
        file_id=file_data.file_id,
        filename=file_data.original_filename,
        file_size=file_data.file_size,
        mime_type=file_data.mime_type
    )


@router.patch("/{file_id}/saved-path")
@inject
async def update_saved_path(
    file_id: str,
    body: SavedPathRequest,
    file_service: FileService = Depends(Provide[AppContainer.file_service]),
):
    """Persist the user-chosen save destination into FileData.metadata + sidecar."""
    if not Path(body.saved_path).is_absolute():
        raise HTTPException(status_code=400, detail="saved_path must be absolute")
    file_service.set_saved_path(file_id, body.saved_path)
    return {"ok": True}
