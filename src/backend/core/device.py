"""
GPU/CPU 自動偵測模組
自動選擇最佳運算裝置和精度設定
支援透過 PyTorch 或 CTranslate2 偵測 CUDA
"""
import logging
from functools import lru_cache

logger = logging.getLogger(__name__)


def _detect_cuda_via_torch() -> str | None:
    """嘗試透過 PyTorch 偵測 CUDA"""
    try:
        import torch

        if torch.cuda.is_available():
            device_name = torch.cuda.get_device_name(0)
            logger.info(f"[PyTorch] Using CUDA device: {device_name}")
            return "cuda"
        elif hasattr(torch.backends, 'mps') and torch.backends.mps.is_available():
            logger.info("[PyTorch] Using Apple Silicon MPS")
            return "mps"
    except ImportError:
        pass
    return None


def _detect_cuda_via_ctranslate2() -> str | None:
    """嘗試透過 CTranslate2 偵測 CUDA"""
    try:
        import ctranslate2

        cuda_count = ctranslate2.get_cuda_device_count()
        if cuda_count > 0:
            logger.info(f"[CTranslate2] CUDA available, {cuda_count} device(s)")
            return "cuda"
    except (ImportError, Exception) as e:
        logger.debug(f"[CTranslate2] CUDA detection failed: {e}")
    return None


@lru_cache(maxsize=1)
def get_device() -> str:
    """
    自動偵測最佳運算裝置
    依序嘗試: PyTorch → CTranslate2 → fallback CPU

    Returns:
        str: "cuda" | "mps" | "cpu"
    """
    # 1. 嘗試 PyTorch 偵測
    device = _detect_cuda_via_torch()
    if device:
        return device

    # 2. 嘗試 CTranslate2 偵測
    device = _detect_cuda_via_ctranslate2()
    if device:
        return device

    # 3. Fallback CPU
    logger.info("Using CPU (no GPU detected)")
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

    # 嘗試透過 PyTorch 取得詳細 GPU 資訊
    try:
        import torch

        if info["device"] == "cuda" and torch.cuda.is_available():
            info["device_name"] = torch.cuda.get_device_name(0)
            info["memory_total"] = torch.cuda.get_device_properties(0).total_memory
            info["memory_free"] = torch.cuda.memory_reserved(0) - torch.cuda.memory_allocated(0)
        elif info["device"] == "mps":
            info["device_name"] = "Apple Silicon"
    except ImportError:
        # PyTorch 未安裝，嘗試透過 nvidia-smi 取得 GPU 名稱
        if info["device"] == "cuda":
            info["device_name"] = _get_gpu_name_via_smi() or "NVIDIA GPU"

    return info


def _get_gpu_name_via_smi() -> str | None:
    """透過 nvidia-smi 取得 GPU 名稱"""
    try:
        import subprocess
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            name = result.stdout.strip().split("\n")[0]
            if name:
                return name
    except Exception:
        pass
    return None
