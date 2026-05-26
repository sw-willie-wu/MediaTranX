"""Video summary API routes."""
from __future__ import annotations
from typing import TYPE_CHECKING, Optional

from dependency_injector.wiring import inject, Provide
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.init.container import AppContainer

if TYPE_CHECKING:
    from app.services.video.summary_service import VideoSummaryService

router = APIRouter()


class VideoSummaryRequest(BaseModel):
    file_id: str = Field(..., description="Input video file ID")

    # LLM — either local (family+size) OR remote (full tuple). Validation
    # in the service layer raises ValueError → HTTP 400.
    llm_model_family: Optional[str] = Field(default=None)        # MODIFIED
    llm_model_size: Optional[str] = Field(default=None)          # MODIFIED
    llm_remote: bool = Field(default=False)                      # NEW
    llm_provider: Optional[str] = Field(default=None)            # NEW
    llm_conn_id: Optional[int] = Field(default=None)             # NEW
    llm_remote_model: Optional[str] = Field(default=None)        # NEW

    language: str = Field(default="zh-TW", description="Content language hint")

    # VLM — wholly optional; if present, either local OR remote.
    vlm_model_family: Optional[str] = Field(default=None)
    vlm_model_size: Optional[str] = Field(default=None)
    vlm_remote: bool = Field(default=False)                      # NEW
    vlm_provider: Optional[str] = Field(default=None)            # NEW
    vlm_conn_id: Optional[int] = Field(default=None)             # NEW
    vlm_remote_model: Optional[str] = Field(default=None)        # NEW

    # Whisper options
    whisper_model_size: str = Field(default="medium", description="Whisper model size")
    vocal_separation: bool = Field(
        default=False, description="Enable Demucs vocal separation"
    )
    align: bool = Field(
        default=False, description="Enable wav2vec2 forced alignment"
    )
    word_timestamps: bool = Field(default=False)
    condition_on_previous_text: bool = Field(default=True)
    min_silence_duration_ms: int = Field(default=200)
    vad_threshold: float = Field(default=0.3)

    summary_mode: str = Field(
        default="bullets",
        description='Output mode: "bullets" (key-points + per-bullet frame) or "narrative" (flat prose paragraphs + per-paragraph frame)',
    )


class VideoSummaryResponse(BaseModel):
    task_id: str
    message: str = "Video summary task submitted"


@router.post("/summary", response_model=VideoSummaryResponse)
@inject
async def summarize_video(
    request: VideoSummaryRequest,
    service: VideoSummaryService = Depends(Provide[AppContainer.video_summary]),
):
    task_id = await service.submit_summary(
        file_id=request.file_id,
        llm_model_family=request.llm_model_family,
        llm_model_size=request.llm_model_size,
        llm_remote=request.llm_remote,                       # NEW
        llm_provider=request.llm_provider,                   # NEW
        llm_conn_id=request.llm_conn_id,                     # NEW
        llm_remote_model=request.llm_remote_model,           # NEW
        language=request.language,
        vlm_model_family=request.vlm_model_family,
        vlm_model_size=request.vlm_model_size,
        vlm_remote=request.vlm_remote,                       # NEW
        vlm_provider=request.vlm_provider,                   # NEW
        vlm_conn_id=request.vlm_conn_id,                     # NEW
        vlm_remote_model=request.vlm_remote_model,           # NEW
        whisper_model_size=request.whisper_model_size,
        vocal_separation=request.vocal_separation,
        align=request.align,
        word_timestamps=request.word_timestamps,
        condition_on_previous_text=request.condition_on_previous_text,
        min_silence_duration_ms=request.min_silence_duration_ms,
        vad_threshold=request.vad_threshold,
        summary_mode=request.summary_mode,
    )
    return VideoSummaryResponse(task_id=task_id)
