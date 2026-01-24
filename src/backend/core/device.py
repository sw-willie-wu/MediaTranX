"""
GPU/CPU 自動偵測模組
自動選擇最佳運算裝置和精度設定
"""
import logging
from functools import lru_cache

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def get_device() -> str:
    """
    自動偵測最佳運算裝置

    Returns:
        str: "cuda" | "mps" | "cpu"
    """
    try:
        import torch

        if torch.cuda.is_available():
            device_name = torch.cuda.get_device_name(0)
            logger.info(f"Using CUDA device: {device_name}")
            return "cuda"
        elif hasattr(torch.backends, 'mps') and torch.backends.mps.is_available():
            logger.info("Using Apple Silicon MPS")
            return "mps"
        else:
            logger.info("Using CPU (no GPU detected)")
            return "cpu"
    except ImportError:
        logger.warning("PyTorch not installed, using CPU")
        return "cpu"


@lru_cache(maxsize=1)
def get_compute_type() -> str:
    """
    根據裝置選擇最佳精度

    Returns:
        str: "float16" for GPU, "int8" for CPU
    """
    device = get_device()
    if device == "cuda":
        return "float16"  # GPU 用半精度加速
    elif device == "mps":
        return "float32"  # MPS 目前較適合 float32
    return "int8"  # CPU 用 int8 量化節省記憶體


def get_device_info() -> dict:
    """
    取得完整的裝置資訊

    Returns:
        dict: 包含裝置類型、名稱、記憶體等資訊
    """
    info = {
        "device": get_device(),
        "compute_type": get_compute_type(),
        "device_name": "CPU",
        "memory_total": None,
        "memory_free": None,
    }

    try:
        import torch

        if info["device"] == "cuda":
            info["device_name"] = torch.cuda.get_device_name(0)
            info["memory_total"] = torch.cuda.get_device_properties(0).total_memory
            info["memory_free"] = torch.cuda.memory_reserved(0) - torch.cuda.memory_allocated(0)
        elif info["device"] == "mps":
            info["device_name"] = "Apple Silicon"
    except ImportError:
        pass

    return info
