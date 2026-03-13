"""
圖片 OCR API 路由（VLM 版）
"""
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.core.ai.ocr import DEFAULT_VLM_MODEL
from app.services.image.ocr_service import get_image_ocr_service

router = APIRouter()


class ImageOcrRequest(BaseModel):
    file_id: str = Field(..., description="輸入檔案 ID")
    model_id: str = Field(default=DEFAULT_VLM_MODEL, description="VLM 模型 ID")
    size: str = Field(default="4b", description="模型大小")
    quantization: Optional[str] = Field(default=None, description="量化格式")
    format: str = Field(default="md", description="輸出格式：txt 或 md")
    output_dir: Optional[str] = Field(default=None, description="自訂輸出目錄")
    output_filename: Optional[str] = Field(default=None, description="自訂輸出檔名")


class ImageOcrResponse(BaseModel):
    task_id: str
    message: str = "OCR 任務已提交"


@router.post("/ocr", response_model=ImageOcrResponse)
async def ocr_image(request: ImageOcrRequest):
    """提交圖片 OCR 任務"""
    try:
        service = get_image_ocr_service()
        task_id = await service.submit_ocr(
            file_id=request.file_id,
            model_id=request.model_id,
            size=request.size,
            quantization=request.quantization,
            format=request.format,
            output_dir=request.output_dir,
            output_filename=request.output_filename,
        )
        return ImageOcrResponse(task_id=task_id)
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
        service = get_image_ocr_service()
        return service.get_status(model_id=model_id, size=size, quantization=quantization)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
