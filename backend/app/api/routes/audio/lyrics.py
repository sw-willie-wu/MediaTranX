"""
Lyrics extraction API routes.
"""
from __future__ import annotations
import logging
from typing import Optional, TYPE_CHECKING

from dependency_injector.wiring import inject, Provide
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.init.container import AppContainer

if TYPE_CHECKING:
    from app.services.audio.lyrics_service import AudioLyricsService

logger = logging.getLogger(__name__)

router = APIRouter()


class LyricsRequest(BaseModel):
    file_id: str = Field(..., description="Input file ID")
    model_size: str = Field(default="medium", description="Whisper model size")
    align: bool = Field(default=False, description="Enable Wav2Vec2 precise alignment")
    translate: bool = Field(default=False, description="Whether to translate lyrics")
    target_language: Optional[str] = Field(default=None, description="Translation target language")
    translate_model_family: str = Field(default="gemma4", description="Translation model family")
    translate_model_size: str = Field(default="4b", description="Translation model size")
    translate_quantization: Optional[str] = Field(default=None, description="Translation model quantization")
    translate_remote: bool = Field(default=False, description="Use cloud translation")
    translate_provider: Optional[str] = Field(default=None, description="Cloud service provider")
    translate_conn_id: Optional[int] = Field(default=None, description="Cloud connection ID")
    translate_remote_model: Optional[str] = Field(default=None, description="Cloud model ID")
    output_format: str = Field(default="lrc", description="Output format (lrc, txt)")
    keep_names: bool = True
    translate_style: str = "colloquial"
    glossary: Optional[dict[str, str]] = None


class LyricsResponse(BaseModel):
    task_id: str
    message: str = "Lyrics extraction task submitted"


@router.post("/lyrics", response_model=LyricsResponse)
@inject
async def extract_lyrics(
    request: LyricsRequest,
    service: AudioLyricsService = Depends(Provide[AppContainer.audio_lyrics]),
):
    task_id = await service.submit_lyrics(
        file_id=request.file_id,
        model_size=request.model_size,
        align=request.align,
        translate=request.translate,
        target_language=request.target_language,
        translate_model_family=request.translate_model_family,
        translate_model_size=request.translate_model_size,
        translate_quantization=request.translate_quantization,
        translate_remote=request.translate_remote,
        translate_provider=request.translate_provider,
        translate_conn_id=request.translate_conn_id,
        translate_remote_model=request.translate_remote_model,
        output_format=request.output_format,
        keep_names=request.keep_names,
        translate_style=request.translate_style,
        glossary=request.glossary,
    )
    return LyricsResponse(task_id=task_id)
