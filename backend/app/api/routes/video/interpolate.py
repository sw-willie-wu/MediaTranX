"""Video interpolation API routes."""
from dependency_injector.wiring import inject, Provide
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from typing import Optional

from app.init.container import AppContainer
from app.services.video.interpolate_service import InterpolateService

router = APIRouter()

class InterpolateRequest(BaseModel):
    file_id: str = Field(..., description="Input file ID")
    model: str = Field(default="v4.22", description="RIFE model variant")
    mode: str = Field(default="2x", description="Interpolation mode (2x, 4x, custom)")
    target_fps: Optional[float] = Field(default=None, description="Target FPS (custom mode)")
    output_format: str = Field(default="mp4", description="Output container format")
    video_codec: str = Field(default="h264", description="Output video codec")
    output_dir: Optional[str] = Field(default=None, description="Output directory")

class InterpolateResponse(BaseModel):
    task_id: str
    message: str = "Interpolation task submitted"

@router.get("/rife/status")
async def rife_status():
    from app.engine.ai.registry import MODELS_REGISTRY, FORMAT_PKG
    from app.init.configs import SETTINGS
    from pathlib import Path
    rife = MODELS_REGISTRY.get(FORMAT_PKG, {}).get("rife", {})
    variants = {}
    for name, spec in rife.get("variants", {}).items():
        model_path = SETTINGS.path.models / "rife" / spec["filename"]
        variants[name] = {"downloaded": model_path.exists()}
    return {"variants": variants}

@router.post("/interpolate", response_model=InterpolateResponse)
@inject
async def interpolate_video(
    request: InterpolateRequest,
    service: InterpolateService = Depends(Provide[AppContainer.video_interpolate]),
):
    try:
        task_id = await service.submit(file_id=request.file_id, model=request.model, mode=request.mode, target_fps=request.target_fps, output_format=request.output_format, video_codec=request.video_codec, output_dir=request.output_dir)
        return InterpolateResponse(task_id=task_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
