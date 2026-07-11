"""Document OCR API routes."""
from __future__ import annotations
from typing import Optional, TYPE_CHECKING

from dependency_injector.wiring import inject, Provide
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.init.container import AppContainer

if TYPE_CHECKING:
    from app.services.document.doc_ocr_service import DocumentOcrService
    from app.services.llm.language_service import LanguageService

router = APIRouter()


class DocumentOcrRequest(BaseModel):
    file_id: str = Field(..., description="Input file ID")
    model_family: Optional[str] = Field(default=None, description="VLM model family (None=use default)")
    model_size: str = Field(default="4b")
    quantization: Optional[str] = Field(default=None)
    output_format: str = Field(default="md", description="Output format: txt or md")
    # Cloud model
    remote: bool = Field(default=False, description="Whether to use a cloud model")
    provider: Optional[str] = Field(default=None, description="Cloud provider")
    conn_id: Optional[int] = Field(default=None, description="Connection ID")
    remote_model: Optional[str] = Field(default=None, description="Cloud model ID")
    suppress_results: Optional[bool] = None


@router.post("/ocr")
@inject
async def ocr_document(
    request: DocumentOcrRequest,
    service: DocumentOcrService = Depends(Provide[AppContainer.doc_ocr]),
    language_service: LanguageService = Depends(Provide[AppContainer.language_service]),
):
    """Submit document OCR task."""
    if request.remote and request.provider and request.remote_model:
        task_id = await service.submit_remote(
            file_id=request.file_id,
            provider=request.provider,
            conn_id=request.conn_id,
            remote_model=request.remote_model,
            output_format=request.output_format,
            suppress_results=request.suppress_results,
        )
    else:
        model_family = request.model_family or language_service.get_default_vlm_model()
        task_id = await service.submit(
            file_id=request.file_id,
            model_family=model_family,
            model_size=request.model_size,
            quantization=request.quantization,
            output_format=request.output_format,
            suppress_results=request.suppress_results,
        )
    return {"task_id": task_id, "message": "OCR task submitted"}


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
    effective_model_family = model_family or language_service.get_default_vlm_model()
    return service.get_status(model_family=effective_model_family, size=size, quantization=quantization)
