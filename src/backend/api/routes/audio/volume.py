from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from backend.services.audio.volume_service import get_audio_volume_service

router = APIRouter()

class AudioVolumeRequest(BaseModel):
    file_id: str = Field(..., description="輸入檔案 ID")
    volume_db: float = Field(default=0.0, ge=-30.0, le=30.0, description="音量調整 dB")
    normalize: bool = Field(default=False, description="響度正規化")

class AudioVolumeResponse(BaseModel):
    task_id: str
    message: str = "音量調整任務已提交"

@router.post("/volume", response_model=AudioVolumeResponse)
async def adjust_volume(request: AudioVolumeRequest):
    try:
        service = get_audio_volume_service()
        task_id = await service.submit_volume(
            file_id=request.file_id,
            volume_db=request.volume_db,
            normalize=request.normalize,
        )
        return AudioVolumeResponse(task_id=task_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
