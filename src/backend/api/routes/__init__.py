from fastapi import APIRouter

from .health import router as health_router
from .files import router as files_router
from .tasks import router as tasks_router

api_router = APIRouter()

api_router.include_router(health_router, tags=["health"])
api_router.include_router(files_router, prefix="/files", tags=["files"])
api_router.include_router(tasks_router, prefix="/tasks", tags=["tasks"])
