"""
檔案處理端點
"""
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pathlib import Path

from backend.services.file_service import get_file_service
from backend.api.schemas.common import FileInfo, FileUploadResponse

router = APIRouter()


@router.post("/upload", response_model=FileUploadResponse)
async def upload_file(
    file: UploadFile = File(...),
    source_dir: Optional[str] = Form(default=None)
):
    """
    上傳檔案

    Args:
        file: 上傳的檔案
        source_dir: 檔案在使用者電腦上的原始目錄（由 Electron 提供）

    Returns:
        FileUploadResponse: 包含 file_id 的回應
    """
    file_service = get_file_service()

    content = await file.read()
    file_info = await file_service.save_upload(
        filename=file.filename or "unnamed",
        content=content,
        mime_type=file.content_type,
        source_dir=source_dir
    )

    return FileUploadResponse(
        file_id=file_info.file_id,
        filename=file_info.original_filename,
        file_size=file_info.file_size,
        mime_type=file_info.mime_type
    )


@router.get("/{file_id}", response_model=FileInfo)
async def get_file_info(file_id: str):
    """
    取得檔案資訊

    Args:
        file_id: 檔案 ID
    """
    file_service = get_file_service()
    file_info = file_service.get_file(file_id)

    if file_info is None:
        raise HTTPException(status_code=404, detail="File not found")

    return file_info


@router.get("/{file_id}/download")
async def download_file(file_id: str):
    """
    下載檔案

    Args:
        file_id: 檔案 ID
    """
    file_service = get_file_service()
    file_info = file_service.get_file(file_id)

    if file_info is None:
        raise HTTPException(status_code=404, detail="File not found")

    file_path = Path(file_info.file_path)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found on disk")

    return FileResponse(
        path=file_path,
        filename=file_info.original_filename,
        media_type=file_info.mime_type
    )


@router.delete("/{file_id}")
async def delete_file(file_id: str):
    """
    刪除檔案

    Args:
        file_id: 檔案 ID
    """
    file_service = get_file_service()

    if not file_service.delete_file(file_id):
        raise HTTPException(status_code=404, detail="File not found")

    return {"status": "deleted", "file_id": file_id}
