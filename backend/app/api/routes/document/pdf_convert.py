"""PDF / 文件轉換 API 路由"""
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.services.document.pdf_convert_service import get_pdf_convert_service

router = APIRouter()


class PdfConvertRequest(BaseModel):
    file_id: str = Field(..., description="輸入檔案 ID")
    output_format: str = Field(default="txt", description="輸出格式：txt / md / images")
    output_dir: Optional[str] = Field(default=None)
    output_filename: Optional[str] = Field(default=None)


@router.post("/pdf-convert")
async def convert_document(request: PdfConvertRequest):
    """提交文件轉換任務"""
    try:
        service = get_pdf_convert_service()
        task_id = await service.submit(
            file_id=request.file_id,
            output_format=request.output_format,
            output_dir=request.output_dir,
            output_filename=request.output_filename,
        )
        return {"task_id": task_id, "message": "轉換任務已提交"}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
