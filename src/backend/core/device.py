"""
GPU/CPU 自動偵測模組
自動選擇最佳運算裝置和精度設定
支援透過 PyTorch 或 CTranslate2 偵測 CUDA
"""
import logging
from functools import lru_cache

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def is_cuda_runtime_available() -> bool:
    """
    檢查 CUDA 運算庫（cublas 等）是否可用

    有 NVIDIA GPU 不代表能跑 CUDA 運算，還需要 CUDA Toolkit 或對應 DLLs。
    PyInstaller 打包後 DLL 在 exe 同目錄，需要額外搜尋。
    """
    import ctypes
    import sys
    from pathlib import Path

    # 1. 標準搜尋（系統 PATH、目前目錄等）
    try:
        ctypes.CDLL("cublas64_12.dll")
        return True
    except (OSError, Exception):
        pass

    # 2. PyInstaller 打包環境：在 exe 目錄搜尋
    if getattr(sys, 'frozen', False):
        exe_dir = Path(sys.executable).parent
        for search_dir in [exe_dir, exe_dir / '_internal']:
            dll_path = search_dir / "cublas64_12.dll"
            if dll_path.exists():
                try:
                    ctypes.CDLL(str(dll_path))
                    return True
                except (OSError, Exception):
                    pass

    return False


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
    except Exception:
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
    額外檢查 CUDA runtime 是否可用（有 GPU 不代表有 CUDA Toolkit）

    Returns:
        str: "cuda" | "mps" | "cpu"
    """
    # 1. 嘗試 PyTorch 偵測
    device = _detect_cuda_via_torch()
    if device == "cuda":
        if is_cuda_runtime_available():
            return "cuda"
        logger.warning("CUDA detected via PyTorch but CUDA runtime (cublas) not available")
    elif device:  # mps
        return device

    # 2. 嘗試 CTranslate2 偵測
    device = _detect_cuda_via_ctranslate2()
    if device == "cuda":
        if is_cuda_runtime_available():
            return "cuda"
        logger.warning("CUDA detected via CTranslate2 but CUDA runtime (cublas) not available")

    # 3. Fallback CPU
    if has_nvidia_gpu():
        logger.info("NVIDIA GPU detected but CUDA Toolkit not installed, falling back to CPU")
    else:
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


_device_info_cache: dict | None = None


def get_device_info() -> dict:
    """
    取得完整的裝置資訊（結果會快取）

    Returns:
        dict: 包含裝置類型、名稱、記憶體等資訊
    """
    global _device_info_cache
    if _device_info_cache is not None:
        return _device_info_cache

    gpu_detected = has_nvidia_gpu()

    # 必須先呼叫 get_device()（內部 import torch 會載入 CUDA DLL），
    # 再呼叫 is_cuda_runtime_available()，否則 @lru_cache 會快取錯誤結果
    device = get_device()
    compute_type = get_compute_type()
    cuda_runtime = is_cuda_runtime_available()

    info = {
        "device": device,
        "compute_type": compute_type,
        "device_name": "CPU",
        "memory_total": None,
        "memory_free": None,
        "has_nvidia_gpu": gpu_detected,
        "cuda_toolkit_installed": cuda_runtime,
    }

    # 嘗試透過 PyTorch 取得詳細 GPU 資訊
    got_gpu_info = False
    try:
        import torch

        if info["device"] == "cuda" and torch.cuda.is_available():
            info["device_name"] = torch.cuda.get_device_name(0)
            info["memory_total"] = torch.cuda.get_device_properties(0).total_memory
            info["memory_free"] = torch.cuda.memory_reserved(0) - torch.cuda.memory_allocated(0)
            got_gpu_info = True
        elif info["device"] == "mps":
            info["device_name"] = "Apple Silicon"
            got_gpu_info = True
    except Exception:
        pass

    # PyTorch 無法取得 GPU 資訊時（未安裝或 CPU 版），改用 nvidia-smi
    if gpu_detected and not got_gpu_info:
        info["device_name"] = _get_gpu_name_via_smi() or "NVIDIA GPU"

    # nvidia-smi fallback: 當 memory_total 仍為 None 且有 NVIDIA GPU 時
    if info["memory_total"] is None and gpu_detected:
        try:
            import subprocess
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=memory.total,memory.free", "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0:
                parts = result.stdout.strip().split(",")
                info["memory_total"] = int(parts[0].strip()) * 1024 * 1024  # MB→bytes
                info["memory_free"] = int(parts[1].strip()) * 1024 * 1024
        except Exception:
            pass

    _device_info_cache = info
    return info


@lru_cache(maxsize=1)
def has_nvidia_gpu() -> bool:
    """
    透過 nvidia-smi 偵測是否有 NVIDIA GPU（不依賴 torch）

    即使 torch 未安裝或只有 CPU 版，仍可偵測到 GPU 硬體。
    """
    try:
        import subprocess
        result = subprocess.run(
            ["nvidia-smi"],
            capture_output=True,
            timeout=5,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


@lru_cache(maxsize=1)
def _get_gpu_name_via_smi() -> str | None:
    """透過 nvidia-smi 取得 GPU 名稱（結果會快取）"""
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
