"""Document OCR API routes."""
from __future__ import annotations
from typing import Optional, TYPE_CHECKING

from dependency_injector.wiring import inject, Provide
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.init.container import AppContainer
from app.services.llm.language_service import LanguageService

if TYPE_CHECKING:
    from app.services.document.doc_ocr_service import DocumentOcrService

router = APIRouter()


class DocumentOcrRequest(BaseModel):
    file_id: str = Field(..., description="Input file ID")
    model_family: Optional[str] = Field(default=None, description="VLM model family (None=use default)")
    size: str = Field(default="4b")
    quantization: Optional[str] = Field(default=None)
    format: str = Field(default="md", description="Output format: txt or md")
    output_dir: Optional[str] = Field(default=None)
    output_filename: Optional[str] = Field(default=None)
    # Cloud model
    remote: bool = Field(default=False, description="Whether to use a cloud model")
    provider: Optional[str] = Field(default=None, description="Cloud provider")
    conn_id: Optional[int] = Field(default=None, description="Connection ID")
    remote_model: Optional[str] = Field(default=None, description="Cloud model ID")


@router.post("/ocr")
@inject
async def ocr_document(
    request: DocumentOcrRequest,
    service: DocumentOcrService = Depends(Provide[AppContainer.doc_ocr]),
    language_service: LanguageService = Depends(Provide[AppContainer.language_service]),
):
    """Submit document OCR task."""
    try:
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
            model_family = request.model_family or language_service.get_default_vlm_model()
            task_id = await service.submit(
                file_id=request.file_id,
                model_family=model_family,
                size=request.size,
                quantization=request.quantization,
                format=request.format,
                output_dir=request.output_dir,
                output_filename=request.output_filename,
            )
        return {"task_id": task_id, "message": "OCR task submitted"}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/ocr/status")
@inject
async def get_ocr_status(
    model_family: Optional[str] = None,
    size: str = "4b",
    quantization: Optional[str] = None,
    service: DocumentOcrService = Depends(Provide[AppContainer.doc_ocr]),
    language_service: LanguageService = Depends(Provide[AppContainer.language_service]),
):
    """Query VLM OCR environment status."""
    try:
        effective_model_family = model_family or language_service.get_default_vlm_model()
        return service.get_status(model_family=effective_model_family, size=size, quantization=quantization)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
