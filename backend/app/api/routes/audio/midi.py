"""
MIDI editor API routes.
"""
from typing import Optional

from dependency_injector.wiring import inject, Provide
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.init.container import AppContainer
from app.services.audio.audio_midi_service import AudioMidiService

router = APIRouter()


class MidiExportRequest(BaseModel):
    file_id: str = Field(..., description="MIDI file ID")
    output_format: str = Field(default="wav", description="輸出格式 (wav, mp3, mid)")
    output_path: Optional[str] = Field(default=None, description="自訂輸出檔案路徑")
    output_dir: Optional[str] = Field(default=None, description="自訂輸出目錄 (deprecated)")


class MidiExportResponse(BaseModel):
    task_id: str
    message: str = "MIDI 匯出任務已提交"


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


@router.post("/midi/export", response_model=MidiExportResponse)
@inject
async def export_midi(
    request: MidiExportRequest,
    service: AudioMidiService = Depends(Provide[AppContainer.audio_midi]),
):
    try:
        task_id = await service.submit_export(
            file_id=request.file_id,
            output_format=request.output_format,
            output_path=request.output_path,
            output_dir=request.output_dir,
        )
        return MidiExportResponse(task_id=task_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
