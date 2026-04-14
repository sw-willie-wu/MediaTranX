from fastapi import APIRouter

from .transcode import router as transcode_router
from .subtitle import router as subtitle_router
from .interpolate import router as interpolate_router
from .enhance import router as enhance_router
from .crop import router as crop_router

router = APIRouter(prefix="/video", tags=["video"])
router.include_router(transcode_router)
router.include_router(subtitle_router)
router.include_router(interpolate_router)
router.include_router(enhance_router)
router.include_router(crop_router)
