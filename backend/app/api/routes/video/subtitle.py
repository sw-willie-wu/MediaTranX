"""
Subtitle extraction API routes.
"""
from __future__ import annotations
import logging
from typing import Optional, TYPE_CHECKING

logger = logging.getLogger(__name__)

from dependency_injector.wiring import inject, Provide
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.init.container import AppContainer
from app.services.setup.language_service import LanguageService

if TYPE_CHECKING:
    from app.services.video.subtitle_service import SubtitleService

router = APIRouter()


class SubtitleGenerateRequest(BaseModel):
    """Subtitle generation request."""
    file_id: str = Field(..., description="Input video file ID")
    language: Optional[str] = Field(
        default=None,
        description="Language code (None=auto-detect, zh=Chinese, en=English, ja=Japanese...)"
    )
    model_size: str = Field(
        default="medium",
        description="Model size (tiny, base, small, medium, large-v3)"
    )
    output_format: str = Field(
        default="srt",
        description="Output format (srt, vtt)"
    )
    output_dir: Optional[str] = Field(default=None, description="Custom output directory")
    output_filename: Optional[str] = Field(default=None, description="Custom output filename")
    target_language: Optional[str] = Field(
        default=None,
        description="Translation target language (None=no translation, zh-TW, en, ja...)"
    )
    translate_model_size: str = Field(
        default="4b",
        description="Translation model size (4b, 12b, 27b)"
    )
    translate_model_type: str = Field(
        default="translategemma",
        description="Translation model type (translategemma, qwen3)"
    )
    translate_quantization: Optional[str] = Field(
        default=None,
        description="Translation model quantization (Q4_K_M, Q4_K_S, Q3_K_L, Q3_K_M, Q3_K_S, Q8_0, etc.)"
    )
    # Advanced segmentation parameters
    word_timestamps: bool = Field(
        default=False,
        description="Enable word-level timestamps (helps with more precise segmentation)"
    )
    condition_on_previous_text: bool = Field(
        default=True,
        description="Condition on previous text (disable to avoid sentence merging, suited for multi-speaker)"
    )
    min_silence_duration_ms: int = Field(
        default=500,
        ge=100,
        le=2000,
        description="Minimum silence duration (ms); pauses shorter than this won't trigger a split"
    )
    vad_threshold: float = Field(
        default=0.5,
        ge=0.1,
        le=0.9,
        description="VAD threshold; lower = more sensitive (more splits)"
    )
    align: bool = Field(
        default=False,
        description="Enable precise alignment (Wav2Vec2 forced alignment)"
    )
    # Translation options
    keep_names: bool = Field(
        default=True,
        description="Keep proper nouns and names in original language"
    )
    translate_style: str = Field(
        default="colloquial",
        description="Translation style: colloquial, formal, or literal"
    )
    glossary: Optional[dict[str, str]] = Field(
        default=None,
        description="Glossary {source_term: translation}"
    )
    # Cloud translation
    translate_remote: bool = Field(default=False, description="Whether to use cloud model for translation")
    translate_provider: Optional[str] = Field(default=None, description="Cloud provider")
    translate_conn_id: Optional[int] = Field(default=None, description="Connection ID")
    translate_remote_model: Optional[str] = Field(default=None, description="Cloud model ID")


class SubtitleGenerateResponse(BaseModel):
    """Subtitle generation response."""
    task_id: str
    message: str = "Subtitle generation task submitted"


class ModelStatusResponse(BaseModel):
    """Model status response (package availability + model download status)."""
    available: bool
    model_size: str
    model_downloaded: bool


@router.get("/whisper/status", response_model=ModelStatusResponse)
@inject
async def get_whisper_status(
    model_size: str = "medium",
    service: SubtitleService = Depends(Provide[AppContainer.video_subtitle]),
):
    """Query Whisper model status."""
    try:
        status = service.get_model_status(model_size)
        return ModelStatusResponse(**status)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/translategemma/status", response_model=ModelStatusResponse)
@inject
async def get_translategemma_status(
    model_size: str = "4b",
    language_service: LanguageService = Depends(Provide[AppContainer.language_service]),
):
    """Query TranslateGemma model status."""
    try:
        status = language_service.get_model_status("translategemma", model_size)
        return ModelStatusResponse(**status)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/translate/status")
@inject
async def get_translate_model_status(
    model_type: str = "translategemma",
    model_size: str = "4b",
    quantization: str | None = None,
    language_service: LanguageService = Depends(Provide[AppContainer.language_service]),
):
    """Query translation model status (generic, supports translategemma and qwen3)."""
    try:
        status = language_service.get_model_status(model_type, model_size, quantization)
        return status
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/translategemma/languages")
@inject
async def get_translategemma_languages(
    language_service: LanguageService = Depends(Provide[AppContainer.language_service]),
):
    """Get the list of languages supported by the translation model."""
    return language_service.get_supported_languages()


class TranslateTestResponse(BaseModel):
    """Translation test response."""
    result: str
    prompt: str


class TranslateTestRequest(BaseModel):
    """Translation test request."""
    text: str = Field(..., description="Text to translate (can be SRT format)")
    target_language: str = Field(default="zh-TW", description="Target language")
    source_language: str = Field(default="ja", description="Source language")
    model_size: str = Field(default="4b", description="Model size: 4b, 12b")


@router.post("/translategemma/test", response_model=TranslateTestResponse)
@inject
async def test_translate(
    request: TranslateTestRequest,
    service: SubtitleService = Depends(Provide[AppContainer.video_subtitle]),
):
    """
    Test translation (for development) -- uses llama-server messages API.
    """
    try:
        data = service.test_translate(
            text=request.text,
            target_language=request.target_language,
            source_language=request.source_language,
            model_size=request.model_size,
        )
        return TranslateTestResponse(result=data["result"], prompt=data["prompt"])
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/subtitle/generate", response_model=SubtitleGenerateResponse)
@inject
async def generate_subtitle(
    request: SubtitleGenerateRequest,
    service: SubtitleService = Depends(Provide[AppContainer.video_subtitle]),
):
    """
    Submit subtitle generation task.

    Uses faster-whisper to extract speech from video and generate subtitle files.
    The specified model is automatically downloaded on first use.
    Optionally translates subtitles to a target language.

    Supported options:
    - **language**: None (auto-detect), zh, en, ja, ko, fr, de, es...
    - **model_size**: tiny, base, small, medium (recommended), large-v3
    - **output_format**: srt (default), vtt
    - **target_language**: None (no translation), zh-TW, en, ja...
    - **translate_model_size**: 4b (recommended), 12b, 27b

    Advanced segmentation options (for multi-speaker scenarios):
    - **word_timestamps**: Enable word-level timestamps
    - **condition_on_previous_text**: Disable to avoid sentence merging
    - **min_silence_duration_ms**: Minimum silence duration (100-2000ms)
    - **vad_threshold**: VAD threshold (0.1-0.9)
    """
    try:
        task_id = await service.submit_subtitle_generate(
            file_id=request.file_id,
            language=request.language,
            model_size=request.model_size,
            output_format=request.output_format,
            output_dir=request.output_dir,
            output_filename=request.output_filename,
            target_language=request.target_language,
            translate_model_size=request.translate_model_size,
            translate_model_type=request.translate_model_type,
            translate_quantization=request.translate_quantization,
            word_timestamps=request.word_timestamps,
            condition_on_previous_text=request.condition_on_previous_text,
            min_silence_duration_ms=request.min_silence_duration_ms,
            vad_threshold=request.vad_threshold,
            keep_names=request.keep_names,
            translate_style=request.translate_style,
            glossary=request.glossary,
            translate_remote=request.translate_remote,
            translate_provider=request.translate_provider,
            translate_conn_id=request.translate_conn_id,
            translate_remote_model=request.translate_remote_model,
        )
        return SubtitleGenerateResponse(task_id=task_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
