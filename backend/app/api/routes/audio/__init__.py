from fastapi import APIRouter
from .transcode import router as transcode_router
from .cut import router as cut_router
from .volume import router as volume_router
from .transcribe import router as transcribe_router
from .separate import router as separate_router

router = APIRouter(prefix="/audio", tags=["audio"])
router.include_router(transcode_router)
router.include_router(cut_router)
router.include_router(volume_router)
router.include_router(transcribe_router)
router.include_router(separate_router)
