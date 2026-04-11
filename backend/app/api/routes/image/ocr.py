"""
Image OCR API routes (VLM-based).
"""
from __future__ import annotations
from typing import Optional, TYPE_CHECKING

from dependency_injector.wiring import inject, Provide
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.init.container import AppContainer
from app.services.setup.language_service import LanguageService

if TYPE_CHECKING:
    from app.services.image.ocr_service import ImageOcrService

router = APIRouter()


class ImageOcrRequest(BaseModel):
    file_id: str = Field(..., description="Input file ID")
    model_id: Optional[str] = Field(default=None, description="VLM model ID (None=use default)")
    size: str = Field(default="4b", description="Model size")
    quantization: Optional[str] = Field(default=None, description="Quantization format")
    format: str = Field(default="md", description="Output format: txt or md")
    output_dir: Optional[str] = Field(default=None, description="Custom output directory")
    output_filename: Optional[str] = Field(default=None, description="Custom output filename")
    # Cloud model
    remote: bool = Field(default=False, description="Whether to use a cloud model")
    provider: Optional[str] = Field(default=None, description="Cloud provider (ollama/openai/gemini)")
    conn_id: Optional[int] = Field(default=None, description="Connection ID")
    remote_model: Optional[str] = Field(default=None, description="Cloud model ID")


class ImageOcrResponse(BaseModel):
    task_id: str
    message: str = "OCR task submitted"


@router.post("/ocr", response_model=ImageOcrResponse)
@inject
async def ocr_image(
    request: ImageOcrRequest,
    service: ImageOcrService = Depends(Provide[AppContainer.image_ocr]),
    language_service: LanguageService = Depends(Provide[AppContainer.language_service]),
):
    """Submit image OCR task."""
    try:
        if request.remote and request.provider and request.remote_model:
            task_id = await service.submit_ocr_remote(
                file_id=request.file_id,
                provider=request.provider,
                conn_id=request.conn_id,
                remote_model=request.remote_model,
                format=request.format,
                output_dir=request.output_dir,
                output_filename=request.output_filename,
            )
        else:
            model_id = request.model_id or language_service.get_default_vlm_model()
            task_id = await service.submit_ocr(
                file_id=request.file_id,
                model_id=model_id,
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
@inject
async def get_ocr_status(
    model_id: Optional[str] = None,
    size: str = "4b",
    quantization: Optional[str] = None,
    service: ImageOcrService = Depends(Provide[AppContainer.image_ocr]),
    language_service: LanguageService = Depends(Provide[AppContainer.language_service]),
):
    """Query VLM OCR environment status."""
    try:
        effective_model_id = model_id or language_service.get_default_vlm_model()
        return service.get_status(model_id=effective_model_id, size=size, quantization=quantization)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
