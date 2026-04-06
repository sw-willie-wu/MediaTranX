"""Video enhancement API routes."""
from dependency_injector.wiring import inject, Provide
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from typing import Optional

from app.init.container import AppContainer
from app.services.video.enhance_service import EnhanceService

router = APIRouter()

class EnhanceRequest(BaseModel):
    file_id: str = Field(..., description="Input file ID")
    model: str = Field(default="realesrgan", description="Enhancement model family")
    variant: str = Field(default="x4plus", description="Model variant")
    output_format: str = Field(default="mp4", description="Output container format")
    video_codec: str = Field(default="h264", description="Output video codec")
    output_dir: Optional[str] = Field(default=None, description="Output directory")

class EnhanceResponse(BaseModel):
    task_id: str
    message: str = "畫面強化任務已提交"

@router.post("/enhance", response_model=EnhanceResponse)
@inject
async def enhance_video(
    request: EnhanceRequest,
    service: EnhanceService = Depends(Provide[AppContainer.video_enhance]),
):
    try:
        task_id = await service.submit(file_id=request.file_id, model=request.model, variant=request.variant, output_format=request.output_format, video_codec=request.video_codec, output_dir=request.output_dir)
        return EnhanceResponse(task_id=task_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
