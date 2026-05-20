"""LLM translate language/style/status endpoints."""
from __future__ import annotations
from typing import TYPE_CHECKING

from dependency_injector.wiring import inject, Provide
from fastapi import APIRouter, Depends

from app.init.container import AppContainer

if TYPE_CHECKING:
    from app.services.llm.language_service import LanguageService


router = APIRouter()


@router.get("/translate/languages")
@inject
async def get_translate_languages(
    language_service: LanguageService = Depends(Provide[AppContainer.language_service]),
):
    """Get the list of languages supported by translation models."""
    return language_service.get_supported_languages()


@router.get("/translate/styles")
@inject
async def get_translate_styles(
    language_service: LanguageService = Depends(Provide[AppContainer.language_service]),
):
    """Get list of translation style options."""
    return language_service.get_translate_styles()


@router.get("/translate/status")
@inject
async def get_translate_model_status(
    model_family: str = "gemma4",
    model_size: str = "4b",
    quantization: str | None = None,
    language_service: LanguageService = Depends(Provide[AppContainer.language_service]),
):
    """Query translation model download/availability status."""
    return language_service.get_model_status(model_family, model_size, quantization)
