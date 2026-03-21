from fastapi import APIRouter
from .active import router as active_router
from .history import router as history_router

router = APIRouter(prefix="/tasks", tags=["tasks"])
router.include_router(history_router)
router.include_router(active_router)
