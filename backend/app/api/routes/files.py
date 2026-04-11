"""
File handling endpoints.
"""
from typing import Optional

from dependency_injector.wiring import inject, Provide
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pathlib import Path
from pydantic import BaseModel

from app.init.container import AppContainer
from app.services.files.file_service import FileService
from app.api.schemas.common import FileInfo, FileUploadResponse

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


class RegisterRequest(BaseModel):
    file_path: str


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
    try:
        file_data = file_service.register_local_file(req.file_path)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))

    return FileUploadResponse(
        file_id=file_data.file_id,
        filename=file_data.original_filename,
        file_size=file_data.file_size,
        mime_type=file_data.mime_type
    )


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
    file_data = file_service.get_file(file_id)

    if file_data is None:
        raise HTTPException(status_code=404, detail="File not found")

    return FileInfo.from_file_data(file_data)


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


@router.post("/cleanup")
@inject
async def cleanup_all_files(
    file_service: FileService = Depends(Provide[AppContainer.file_service]),
):
    """
    Clean up all temporary and output files for this session.
    Called by Electron before the application closes (when autoCleanTemp is enabled).
    """
    count = file_service.cleanup_all()
    return {"status": "ok", "deleted": count}


@router.delete("/{file_id}")
@inject
async def delete_file(
    file_id: str,
    file_service: FileService = Depends(Provide[AppContainer.file_service]),
):
    """
    Delete a file.

    Args:
        file_id: File ID
    """
    if not file_service.delete_file(file_id):
        raise HTTPException(status_code=404, detail="File not found")

    return {"status": "deleted", "file_id": file_id}
