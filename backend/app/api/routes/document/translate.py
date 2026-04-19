"""
Document translation API routes.
"""
from __future__ import annotations
from typing import Optional, TYPE_CHECKING

from dependency_injector.wiring import inject, Provide
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.init.container import AppContainer

if TYPE_CHECKING:
    from app.services.document.translate_service import TranslateService

router = APIRouter()


class DocumentTranslateRequest(BaseModel):
    """Document translation request."""
    file_id: str = Field(..., description="Input file ID")
    source_language: str = Field(..., description="Source language (BCP 47)")
    target_language: str = Field(..., description="Target language (BCP 47)")
    model_size: str = Field(default="4b", description="Model size (4b, 12b, 27b)")
    model_family: str = Field(default="gemma4", description="Translation model family (qwen3, gemma4, qwen3.5)")
    quantization: Optional[str] = Field(default=None, description="Model quantization (Q4_K_M, Q3_K_M, etc.)")
    translate_style: str = Field(default="colloquial", description="Translation style (colloquial, formal, literal)")
    glossary: Optional[dict[str, str]] = Field(default=None, description="Glossary {source_term: translation}")


class DocumentTranslateResponse(BaseModel):
    """Document translation response."""
    task_id: str
    message: str = "Document translation task submitted"



@router.post("/translate", response_model=DocumentTranslateResponse)
@inject
async def translate_document(
    request: DocumentTranslateRequest,
    service: TranslateService = Depends(Provide[AppContainer.doc_translate]),
):
    """
    Submit document translation task.

    Translates uploaded text files using local LLM.
    The specified model is automatically downloaded on first use.
    """
    task_id = await service.submit_translate(
        file_id=request.file_id,
        source_language=request.source_language,
        target_language=request.target_language,
        model_size=request.model_size,
        model_family=request.model_family,
        quantization=request.quantization,
        translate_style=request.translate_style,
        glossary=request.glossary,
    )
    return DocumentTranslateResponse(task_id=task_id)
