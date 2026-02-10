from fastapi import APIRouter

from .translate import router as translate_router

router = APIRouter(prefix="/document", tags=["document"])
router.include_router(translate_router)
