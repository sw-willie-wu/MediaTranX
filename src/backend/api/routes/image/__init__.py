from fastapi import APIRouter
from .convert import router as convert_router

router = APIRouter(prefix="/image", tags=["image"])
router.include_router(convert_router)
