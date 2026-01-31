from fastapi import APIRouter
from .transcode import router as transcode_router

router = APIRouter(prefix="/audio", tags=["audio"])
router.include_router(transcode_router)
