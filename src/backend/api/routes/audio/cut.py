from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from backend.services.audio.cut_service import get_audio_cut_service

router = APIRouter()

class AudioCutRequest(BaseModel):
    file_id: str = Field(..., description="輸入檔案 ID")
    start_time: str = Field(default="00:00:00", description="開始時間 HH:MM:SS")
    end_time: str = Field(..., description="結束時間 HH:MM:SS")

class AudioCutResponse(BaseModel):
    task_id: str
    message: str = "音訊剪輯任務已提交"

@router.post("/cut", response_model=AudioCutResponse)
async def cut_audio(request: AudioCutRequest):
    try:
        service = get_audio_cut_service()
        task_id = await service.submit_cut(
            file_id=request.file_id,
            start_time=request.start_time,
            end_time=request.end_time,
        )
        return AudioCutResponse(task_id=task_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
