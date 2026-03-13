from fastapi import APIRouter
from .convert import router as convert_router
from .upscale import router as upscale_router
from .remove_bg import router as remove_bg_router
from .remove_object import router as remove_object_router
from .filter import router as filter_router
from .crop import router as crop_router
from .compress import router as compress_router
from .ocr import router as ocr_router

router = APIRouter(prefix="/image", tags=["image"])
router.include_router(convert_router)
router.include_router(upscale_router)
router.include_router(remove_bg_router)
router.include_router(remove_object_router)
router.include_router(filter_router)
router.include_router(crop_router)
router.include_router(compress_router)
router.include_router(ocr_router)
