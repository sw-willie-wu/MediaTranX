"""
健康檢查端點
"""
from fastapi import APIRouter
from app.services.setup.device_service import get_device_service

router = APIRouter()


@router.get("/health")
async def health_check():
    """健康檢查"""
    return {"status": "ok"}


@router.get("/device")
async def device_info():
    """取得裝置資訊（GPU/CPU）"""
    return get_device_service().get_device_info()


@router.post("/device/refresh")
async def refresh_device():
    """清除裝置快取並重新偵測（CUDA DLL 安裝後呼叫）"""
    service = get_device_service()
    service.refresh_cache()
    return service.get_device_info()
