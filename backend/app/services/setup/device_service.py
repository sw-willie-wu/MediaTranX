"""
裝置資訊服務
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
包裝 engine.device 的查詢功能，提供給 Route 層使用。
Route 不應直接 import engine.device。
"""
import logging
logger = logging.getLogger(__name__)


class DeviceService:
    """裝置資訊查詢服務"""

    def __init__(self):
        logger.info("DeviceService initialized")

    def get_device_info(self) -> dict:
        """取得完整的裝置資訊"""
        from app.engine.device import get_device_info
        return get_device_info()

    def refresh_cache(self) -> None:
        """清除裝置偵測快取，強制重新偵測"""
        from app.engine.device import refresh_device_cache
        refresh_device_cache()

    def get_device(self) -> str:
        """取得目前使用的運算裝置（cuda/dml/cpu）"""
        from app.engine.device import get_device
        return get_device()

    def get_compute_type(self) -> str:
        """取得目前的計算精度（float16/int8/float32）"""
        from app.engine.device import get_compute_type
        return get_compute_type()

    def select_torch_index(self) -> str:
        """根據驅動版本選擇 PyTorch wheel 類型"""
        from app.engine.device import select_torch_index
        return select_torch_index()
