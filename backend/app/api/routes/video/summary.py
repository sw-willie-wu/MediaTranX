"""Video summary API routes."""
from __future__ import annotations
from typing import TYPE_CHECKING, Optional

from dependency_injector.wiring import inject, Provide
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.init.container import AppContainer

if TYPE_CHECKING:
    from app.services.video.summary import VideoSummaryService

router = APIRouter()


class VideoSummaryRequest(BaseModel):
    file_id: str = Field(..., description="Input video file ID")
    llm_model_family: str = Field(..., description="Text-capable LLM family (e.g. qwen3.5)")
    llm_model_size: str = Field(..., description="LLM model size (e.g. 9b)")
    language: str = Field(default="zh-TW", description="Content language hint")
    vlm_model_family: Optional[str] = Field(
        default=None,
        description="Vision-capable model family (optional; enables VLM frame selection)",
    )
    vlm_model_size: Optional[str] = Field(default=None)

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
        description='Output mode: "bullets" (key-points + per-bullet frame) or "narrative" (prose summary + turning-point frames)',
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
        language=request.language,
        vlm_model_family=request.vlm_model_family,
        vlm_model_size=request.vlm_model_size,
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
