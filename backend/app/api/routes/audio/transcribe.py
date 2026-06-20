from __future__ import annotations
import logging
from typing import Optional, TYPE_CHECKING

from dependency_injector.wiring import inject, Provide
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.init.container import AppContainer

if TYPE_CHECKING:
    from app.services.audio.transcribe_service import AudioTranscribeService
    from app.services.llm.language_service import LanguageService

logger = logging.getLogger(__name__)

router = APIRouter()

class AudioTranscribeRequest(BaseModel):
    file_id: str = Field(..., description="Input file ID")
    source_language: Optional[str] = Field(default=None, description="Language code, None=auto-detect")
    model_size: str = Field(default="medium", description="Whisper model size")
    output_format: str = Field(default="txt", description="Output format (txt, srt)")
    vocal_separation: bool = Field(default=False, description="Vocal separation preprocessing")
    align: bool = Field(default=False, description="Precise alignment")
    translate: bool = Field(default=False, description="Translation")
    target_language: Optional[str] = Field(default=None, description="Translation target language")
    translate_model_family: str = Field(default="gemma4", description="Translation model family")
    translate_model_size: str = Field(default="4b", description="Translation model size")
    translate_quantization: Optional[str] = Field(default=None, description="Translation model quantization")
    translate_remote: bool = Field(default=False, description="Use cloud translation")
    translate_provider: Optional[str] = Field(default=None, description="Cloud service provider")
    translate_conn_id: Optional[int] = Field(default=None, description="Cloud connection ID")
    translate_remote_model: Optional[str] = Field(default=None, description="Cloud model ID")
    summarize: bool = Field(default=False, description="Outline summarization")
    summarize_model_family: str = Field(default="gemma4", description="Summarization model family")
    summarize_model_size: str = Field(default="4b", description="Summarization model size")
    summarize_quantization: Optional[str] = Field(default=None, description="Summarization model quantization")
    summarize_remote: bool = Field(default=False, description="Use cloud summarization model")
    summarize_provider: Optional[str] = Field(default=None, description="Cloud service provider")
    summarize_conn_id: Optional[int] = Field(default=None, description="Cloud connection ID")
    summarize_remote_model: Optional[str] = Field(default=None, description="Cloud model ID")
    # whisper inference params (A1)
    word_timestamps: bool = Field(default=False, description="Word-level timestamps")
    condition_on_previous_text: bool = Field(default=True, description="Condition on previous text")
    min_silence_duration_ms: int = Field(default=200, description="Minimum silence duration (ms)")
    vad_threshold: float = Field(default=0.3, description="VAD probability threshold")
    # translation sub-params (A2)
    keep_names: bool = Field(default=True, description="Preserve proper names in translation")
    translate_style: str = Field(default="colloquial", description="Translation style")
    glossary: Optional[dict[str, str]] = Field(default=None, description="Term glossary for translation")

class AudioTranscribeResponse(BaseModel):
    task_id: str
    message: str = "Transcription task submitted"

@router.get("/transcribe/languages")
@inject
async def get_transcribe_languages(
    language_service: LanguageService = Depends(Provide[AppContainer.language_service]),
):
    """Get the list of languages supported by Whisper."""
    return language_service.get_whisper_languages()


@router.get("/transcribe/status")
@inject
async def get_transcribe_status(
    model_size: str = "medium",
    service: AudioTranscribeService = Depends(Provide[AppContainer.audio_transcribe]),
):
    return service.get_model_status(model_size)

@router.post("/transcribe", response_model=AudioTranscribeResponse)
@inject
async def transcribe_audio(
    request: AudioTranscribeRequest,
    service: AudioTranscribeService = Depends(Provide[AppContainer.audio_transcribe]),
):
    task_id = await service.submit_transcribe(
        file_id=request.file_id,
        source_language=request.source_language,
        model_size=request.model_size,
        output_format=request.output_format,
        vocal_separation=request.vocal_separation,
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
        summarize=request.summarize,
        summarize_model_family=request.summarize_model_family,
        summarize_model_size=request.summarize_model_size,
        summarize_quantization=request.summarize_quantization,
        summarize_remote=request.summarize_remote,
        summarize_provider=request.summarize_provider,
        summarize_conn_id=request.summarize_conn_id,
        summarize_remote_model=request.summarize_remote_model,
        word_timestamps=request.word_timestamps,
        condition_on_previous_text=request.condition_on_previous_text,
        min_silence_duration_ms=request.min_silence_duration_ms,
        vad_threshold=request.vad_threshold,
        keep_names=request.keep_names,
        translate_style=request.translate_style,
        glossary=request.glossary,
    )
    return AudioTranscribeResponse(task_id=task_id)
