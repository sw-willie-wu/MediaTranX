from fastapi import APIRouter

from .translate import router as translate_router
from .pdf_convert import router as pdf_convert_router
from .ocr import router as ocr_router
from .split import router as split_router

router = APIRouter(prefix="/document", tags=["document"])
router.include_router(translate_router)
router.include_router(pdf_convert_router)
router.include_router(ocr_router)
router.include_router(split_router)
