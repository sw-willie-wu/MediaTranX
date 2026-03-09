from fastapi import APIRouter
from .convert import router as convert_router
from .upscale import router as upscale_router

router = APIRouter(prefix="/image", tags=["image"])
router.include_router(convert_router)
router.include_router(upscale_router)
