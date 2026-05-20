"""
Device information service.
Wraps adapters.device query functions for the route layer.
Routes should not import adapters.device directly.
"""
import logging
logger = logging.getLogger(__name__)


class DeviceService:
    """Hardware device detection and compute capability query service."""

    def __init__(self):
        logger.info("DeviceService initialized")

    def get_device_info(self) -> dict:
        """Get complete device information."""
        from app.adapters.device import get_device_info
        return get_device_info()

    def refresh_cache(self) -> None:
        """Clear device detection cache and force re-detection."""
        from app.adapters.device import refresh_device_cache
        refresh_device_cache()

    def get_device(self) -> str:
        """Get the current compute device (cuda/dml/cpu)."""
        from app.adapters.device import get_device
        return get_device()

    def get_compute_type(self) -> str:
        """Get the current compute type (float16/int8/float32)."""
        from app.adapters.device import get_compute_type
        return get_compute_type()

    def select_torch_index(self) -> str:
        """Select PyTorch wheel type based on driver version."""
        from app.adapters.device import select_torch_index
        return select_torch_index()
