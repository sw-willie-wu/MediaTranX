from __future__ import annotations
from typing import Optional, List, TYPE_CHECKING

from dependency_injector.wiring import inject, Provide
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.init.container import AppContainer

if TYPE_CHECKING:
    from app.services.audio.separate_service import AudioSeparateService

router = APIRouter()


class AudioSeparateRequest(BaseModel):
    file_id: str = Field(..., description="Input file ID")
    model_name: str = Field(default="htdemucs_6s", description="Demucs model name")
    stems: Optional[List[str]] = Field(default=None, description="Stems to separate (None=all)")
    output_format: str = Field(default="wav", description="Output format (wav, flac, mp3)")
    output_dir: Optional[str] = Field(default=None, description="Custom output directory")
    output_filename: Optional[str] = Field(default=None, description="Custom output filename (for the primary stem file)")
    generate_midi: bool = Field(default=False, description="Also generate multi-track MIDI file")


class AudioSeparateResponse(BaseModel):
    task_id: str
    message: str = "Audio separation task submitted"


@router.get("/separate/status")
@inject
async def get_separate_status(
    model_name: str = "htdemucs_6s",
    service: AudioSeparateService = Depends(Provide[AppContainer.audio_separate]),
):
    try:
        return service.get_model_status(model_name)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/separate", response_model=AudioSeparateResponse)
@inject
async def separate_audio(
    request: AudioSeparateRequest,
    service: AudioSeparateService = Depends(Provide[AppContainer.audio_separate]),
):
    try:
        task_id = await service.submit_separate(
            file_id=request.file_id,
            model_name=request.model_name,
            stems=request.stems,
            output_format=request.output_format,
            output_dir=request.output_dir,
            output_filename=request.output_filename,
            generate_midi=request.generate_midi,
        )
        return AudioSeparateResponse(task_id=task_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
