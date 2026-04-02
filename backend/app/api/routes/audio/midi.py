"""
MIDI editor API routes.
"""
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.services.audio.audio_midi_service import get_audio_midi_service

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
async def create_midi(request: MidiSaveRequest):
    """Create a new MIDI file from editor data, returns file_id."""
    try:
        service = get_audio_midi_service()
        file_id = service.create_midi(request.data)
        return {"file_id": file_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/midi/{file_id}")
async def read_midi(file_id: str):
    try:
        service = get_audio_midi_service()
        return service.read_midi(file_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/midi/{file_id}")
async def save_midi(file_id: str, request: MidiSaveRequest):
    try:
        service = get_audio_midi_service()
        return service.save_midi(file_id, request.data)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/midi/export", response_model=MidiExportResponse)
async def export_midi(request: MidiExportRequest):
    try:
        service = get_audio_midi_service()
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
