"""
健康檢查端點
"""
from fastapi import APIRouter
from backend.core.device import get_device_info, refresh_device_cache

router = APIRouter()


@router.get("/health")
async def health_check():
    """健康檢查"""
    return {"status": "ok"}


@router.get("/device")
async def device_info():
    """取得裝置資訊（GPU/CPU）"""
    return get_device_info()


@router.post("/device/refresh")
async def refresh_device():
    """清除裝置快取並重新偵測（CUDA DLL 安裝後呼叫）"""
    refresh_device_cache()
    return get_device_info()
