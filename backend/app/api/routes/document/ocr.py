"""文件 OCR API 路由"""
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.services.document.doc_ocr_service import get_doc_ocr_service
from app.services.setup.language_service import get_language_service

router = APIRouter()


class DocumentOcrRequest(BaseModel):
    file_id: str = Field(..., description="輸入檔案 ID")
    model_id: Optional[str] = Field(default=None, description="VLM 模型 ID（None=使用預設）")
    size: str = Field(default="4b")
    quantization: Optional[str] = Field(default=None)
    format: str = Field(default="md", description="輸出格式：txt 或 md")
    output_dir: Optional[str] = Field(default=None)
    output_filename: Optional[str] = Field(default=None)
    # 雲端模型
    remote: bool = Field(default=False, description="是否使用雲端模型")
    provider: Optional[str] = Field(default=None, description="雲端 provider")
    conn_id: Optional[int] = Field(default=None, description="連線 ID")
    remote_model: Optional[str] = Field(default=None, description="雲端模型 ID")


@router.post("/ocr")
async def ocr_document(request: DocumentOcrRequest):
    """提交文件 OCR 任務"""
    try:
        service = get_doc_ocr_service()
        if request.remote and request.provider and request.remote_model:
            task_id = await service.submit_remote(
                file_id=request.file_id,
                provider=request.provider,
                conn_id=request.conn_id,
                remote_model=request.remote_model,
                format=request.format,
                output_dir=request.output_dir,
                output_filename=request.output_filename,
            )
        else:
            model_id = request.model_id or get_language_service().get_default_vlm_model()
            task_id = await service.submit(
                file_id=request.file_id,
                model_id=model_id,
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
    model_id: Optional[str] = None,
    size: str = "4b",
    quantization: Optional[str] = None,
):
    """查詢 VLM OCR 環境狀態"""
    try:
        effective_model_id = model_id or get_language_service().get_default_vlm_model()
        service = get_doc_ocr_service()
        return service.get_status(model_id=effective_model_id, size=size, quantization=quantization)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
