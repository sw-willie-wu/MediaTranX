"""
Document translation API routes.
"""
from __future__ import annotations
from typing import Optional, TYPE_CHECKING

from dependency_injector.wiring import inject, Provide
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.init.container import AppContainer
from app.services.setup.language_service import LanguageService

if TYPE_CHECKING:
    from app.services.document.translate_service import TranslateService

router = APIRouter()


class DocumentTranslateRequest(BaseModel):
    """Document translation request."""
    file_id: str = Field(..., description="Input file ID")
    source_language: str = Field(..., description="Source language (BCP 47)")
    target_language: str = Field(..., description="Target language (BCP 47)")
    model_size: str = Field(default="4b", description="Model size (4b, 12b, 27b)")
    model_type: str = Field(default="translategemma", description="Translation model type (translategemma, qwen3)")
    quantization: Optional[str] = Field(default=None, description="Model quantization (Q4_K_M, Q3_K_M, etc.)")
    translate_style: str = Field(default="colloquial", description="Translation style (colloquial, formal, literal)")
    glossary: Optional[dict[str, str]] = Field(default=None, description="Glossary {source_term: translation}")
    output_dir: Optional[str] = Field(default=None, description="Custom output directory")
    output_filename: Optional[str] = Field(default=None, description="Custom output filename")


class DocumentTranslateResponse(BaseModel):
    """Document translation response."""
    task_id: str
    message: str = "Document translation task submitted"


class TranslateGemmaStatusResponse(BaseModel):
    """TranslateGemma model status response."""
    available: bool
    model_size: str
    model_downloaded: bool


@router.get("/translategemma/status", response_model=TranslateGemmaStatusResponse)
@inject
async def get_translategemma_status(
    model_type: str = "translategemma",
    model_size: str = "4b",
    language_service: LanguageService = Depends(Provide[AppContainer.language_service]),
):
    """Query translation model status."""
    try:
        status = language_service.get_model_status(model_type, model_size)
        return TranslateGemmaStatusResponse(**status)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/translategemma/languages")
@inject
async def get_translategemma_languages(
    language_service: LanguageService = Depends(Provide[AppContainer.language_service]),
):
    """Get the list of languages supported by TranslateGemma."""
    return language_service.get_supported_languages()


@router.post("/translate", response_model=DocumentTranslateResponse)
@inject
async def translate_document(
    request: DocumentTranslateRequest,
    service: TranslateService = Depends(Provide[AppContainer.doc_translate]),
):
    """
    Submit document translation task.

    Translates uploaded text files using TranslateGemma.
    The specified model is automatically downloaded on first use.
    """
    try:
        task_id = await service.submit_translate(
            file_id=request.file_id,
            source_language=request.source_language,
            target_language=request.target_language,
            model_size=request.model_size,
            model_type=request.model_type,
            quantization=request.quantization,
            translate_style=request.translate_style,
            glossary=request.glossary,
            output_dir=request.output_dir,
            output_filename=request.output_filename,
        )
        return DocumentTranslateResponse(task_id=task_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
