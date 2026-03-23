from typing import Optional, List
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from app.services.audio.separate_service import get_audio_separate_service

router = APIRouter()


class AudioSeparateRequest(BaseModel):
    file_id: str = Field(..., description="輸入檔案 ID")
    model_name: str = Field(default="htdemucs_6s", description="Demucs 模型名稱")
    stems: Optional[List[str]] = Field(default=None, description="要分離的音軌 (None=全部)")


class AudioSeparateResponse(BaseModel):
    task_id: str
    message: str = "音源分離任務已提交"


@router.get("/separate/status")
async def get_separate_status(model_name: str = "htdemucs_6s"):
    try:
        service = get_audio_separate_service()
        return service.get_model_status(model_name)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/separate", response_model=AudioSeparateResponse)
async def separate_audio(request: AudioSeparateRequest):
    try:
        service = get_audio_separate_service()
        task_id = await service.submit_separate(
            file_id=request.file_id,
            model_name=request.model_name,
            stems=request.stems,
        )
        return AudioSeparateResponse(task_id=task_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
