from typing import Optional

from dependency_injector.wiring import inject, Provide
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.init.container import AppContainer
from app.services.audio.cut_service import AudioCutService

router = APIRouter()

class AudioCutRequest(BaseModel):
    file_id: str = Field(..., description="輸入檔案 ID")
    start_time: str = Field(default="00:00:00", description="開始時間 HH:MM:SS")
    end_time: str = Field(..., description="結束時間 HH:MM:SS")
    output_dir: Optional[str] = Field(default=None, description="自訂輸出目錄")
    output_filename: Optional[str] = Field(default=None, description="自訂輸出檔名")

class AudioCutResponse(BaseModel):
    task_id: str
    message: str = "音訊剪輯任務已提交"

@router.post("/cut", response_model=AudioCutResponse)
@inject
async def cut_audio(
    request: AudioCutRequest,
    service: AudioCutService = Depends(Provide[AppContainer.audio_cut]),
):
    try:
        task_id = await service.submit_cut(
            file_id=request.file_id,
            start_time=request.start_time,
            end_time=request.end_time,
            output_dir=request.output_dir,
            output_filename=request.output_filename,
        )
        return AudioCutResponse(task_id=task_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
