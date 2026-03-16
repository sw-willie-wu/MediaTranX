"""PDF 分割 API 路由"""
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.services.document.split_service import get_split_service

router = APIRouter()


class DocumentSplitRequest(BaseModel):
    file_id: str = Field(..., description="輸入 PDF 檔案 ID")
    pages: str = Field(default="", description="頁碼範圍，例如 '1-3,5,7-9'，空白表示全部頁面")
    output_dir: Optional[str] = Field(default=None)
    output_filename: Optional[str] = Field(default=None)


@router.post("/split")
async def split_document(request: DocumentSplitRequest):
    """提交 PDF 分割任務"""
    try:
        service = get_split_service()
        task_id = await service.submit(
            file_id=request.file_id,
            pages=request.pages,
            output_dir=request.output_dir,
            output_filename=request.output_filename,
        )
        return {"task_id": task_id, "message": "PDF 分割任務已提交"}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
