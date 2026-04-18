"""Health + device routes aggregator."""
from fastapi import APIRouter

from .device import router as device_router
from .health import router as health_router

router = APIRouter()
router.include_router(health_router)
router.include_router(device_router)
