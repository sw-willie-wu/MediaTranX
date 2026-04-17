"""
MIDI editor API routes.
"""
from __future__ import annotations
from typing import TYPE_CHECKING, Optional

from dependency_injector.wiring import inject, Provide
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

from app.init.container import AppContainer

if TYPE_CHECKING:
    from app.services.audio.audio_midi_service import AudioMidiService

router = APIRouter()


class MidiSaveRequest(BaseModel):
    data: dict = Field(..., description="MIDI JSON data")


@router.post("/midi/create")
@inject
async def create_midi(
    request: MidiSaveRequest,
    service: AudioMidiService = Depends(Provide[AppContainer.audio_midi]),
):
    """Create a new MIDI file from editor data, returns file_id."""
    file_id = service.create_midi(request.data)
    return {"file_id": file_id}


@router.get("/midi/{file_id}")
@inject
async def read_midi(
    file_id: str,
    service: AudioMidiService = Depends(Provide[AppContainer.audio_midi]),
):
    return service.read_midi(file_id)


@router.put("/midi/{file_id}")
@inject
async def save_midi(
    file_id: str,
    request: MidiSaveRequest,
    service: AudioMidiService = Depends(Provide[AppContainer.audio_midi]),
):
    return service.save_midi(file_id, request.data)


@router.post("/midi/convert")
@inject
async def convert_audio(
    file: UploadFile = File(...),
    format: str = Form("mp3"),
    source_file_id: Optional[str] = Form(None),
    service: AudioMidiService = Depends(Provide[AppContainer.audio_midi]),
):
    """Convert uploaded audio to target format; register as Results output.

    Returns `output_file_id` which the frontend can fetch via /files/{id}.
    """
    return await service.convert_wav(file, format, source_file_id)
