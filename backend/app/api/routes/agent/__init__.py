"""Agent routes aggregator."""
from fastapi import APIRouter

from .run import router as run_router
from .sessions import router as sessions_router

router = APIRouter()
router.include_router(run_router)
router.include_router(sessions_router)
