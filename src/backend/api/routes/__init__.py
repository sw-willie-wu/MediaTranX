from fastapi import APIRouter

from .health import router as health_router
from .files import router as files_router
from .tasks import router as tasks_router
from .video import router as video_router
from .audio import router as audio_router
from .image import router as image_router

api_router = APIRouter()

api_router.include_router(health_router, tags=["health"])
api_router.include_router(files_router, prefix="/files", tags=["files"])
api_router.include_router(tasks_router, prefix="/tasks", tags=["tasks"])
api_router.include_router(video_router)
api_router.include_router(audio_router)
api_router.include_router(image_router)
