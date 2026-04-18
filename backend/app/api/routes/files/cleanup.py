"""File cleanup + delete endpoints."""
from __future__ import annotations
from typing import TYPE_CHECKING

from dependency_injector.wiring import inject, Provide
from fastapi import APIRouter, Depends, HTTPException

from app.init.container import AppContainer

if TYPE_CHECKING:
    from app.services.files.file_service import FileService


router = APIRouter()


@router.post("/cleanup")
@inject
async def cleanup_all_files(
    file_service: FileService = Depends(Provide[AppContainer.file_service]),
):
    """
    Clean up all temporary files (uploads + outputs + sidecars).
    Invoked manually via Settings > "Clear temp files" button.
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
