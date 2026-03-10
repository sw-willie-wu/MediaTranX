"""文件 OCR API 路由"""
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.core.ai.ocr import DEFAULT_VLM_MODEL
from backend.services.document.doc_ocr_service import get_doc_ocr_service

router = APIRouter()


class DocumentOcrRequest(BaseModel):
    file_id: str = Field(..., description="輸入檔案 ID")
    model_id: str = Field(default=DEFAULT_VLM_MODEL)
    size: str = Field(default="4b")
    quantization: Optional[str] = Field(default=None)
    format: str = Field(default="md", description="輸出格式：txt 或 md")
    output_dir: Optional[str] = Field(default=None)
    output_filename: Optional[str] = Field(default=None)


@router.post("/ocr")
async def ocr_document(request: DocumentOcrRequest):
    """提交文件 OCR 任務"""
    try:
        service = get_doc_ocr_service()
        task_id = await service.submit(
            file_id=request.file_id,
            model_id=request.model_id,
            size=request.size,
            quantization=request.quantization,
            format=request.format,
            output_dir=request.output_dir,
            output_filename=request.output_filename,
        )
        return {"task_id": task_id, "message": "OCR 任務已提交"}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/ocr/status")
async def get_ocr_status(
    model_id: str = DEFAULT_VLM_MODEL,
    size: str = "4b",
    quantization: Optional[str] = None,
):
    """查詢 VLM OCR 環境狀態"""
    try:
        service = get_doc_ocr_service()
        return service.get_status(model_id=model_id, size=size, quantization=quantization)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
