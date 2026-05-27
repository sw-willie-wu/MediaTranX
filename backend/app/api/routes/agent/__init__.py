"""Agent routes aggregator."""
from fastapi import APIRouter

from .run import router as run_router

router = APIRouter()
router.include_router(run_router)
