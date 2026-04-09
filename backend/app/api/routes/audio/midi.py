"""
MIDI editor API routes.
"""
from dependency_injector.wiring import inject, Provide
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

from app.init.container import AppContainer
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
    try:
        file_id = service.create_midi(request.data)
        return {"file_id": file_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/midi/{file_id}")
@inject
async def read_midi(
    file_id: str,
    service: AudioMidiService = Depends(Provide[AppContainer.audio_midi]),
):
    try:
        return service.read_midi(file_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/midi/{file_id}")
@inject
async def save_midi(
    file_id: str,
    request: MidiSaveRequest,
    service: AudioMidiService = Depends(Provide[AppContainer.audio_midi]),
):
    try:
        return service.save_midi(file_id, request.data)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/midi/convert")
@inject
async def convert_audio(
    file: UploadFile = File(...),
    format: str = Form("mp3"),
    output_path: str = Form(...),
    service: AudioMidiService = Depends(Provide[AppContainer.audio_midi]),
):
    """Convert uploaded WAV to target format via FFmpeg."""
    result = await service.convert_wav(file, format, output_path)
    return result
