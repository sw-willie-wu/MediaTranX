from fastapi import APIRouter

from .transcode import router as transcode_router
from .subtitle import router as subtitle_router

router = APIRouter(prefix="/video", tags=["video"])
router.include_router(transcode_router)
router.include_router(subtitle_router)
