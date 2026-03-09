"""
GPU/CPU 自動偵測模組
自動選擇最佳運算裝置和精度設定
支援透過 PyTorch 或 CTranslate2 偵測 CUDA
"""
import sys
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

    # 3. 使用者下載的 CUDA DLL（%APPDATA%/MediaTranX/cuda/）
    # 用絕對路徑載入，避免 frozen 環境 PATH 搜尋不可靠的問題
    try:
        import os
        appdata = os.environ.get('APPDATA', '')
        if appdata:
            cuda_dll = Path(appdata) / 'MediaTranX' / 'cuda' / 'cublas64_12.dll'
            if cuda_dll.exists():
                # 先把目錄加入 AddDllDirectory，讓依賴 DLL（cudart 等）也能被找到
                try:
                    os.add_dll_directory(str(cuda_dll.parent))
                except (AttributeError, OSError):
                    pass
                ctypes.CDLL(str(cuda_dll))
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


def has_directml() -> bool:
    """
    偵測是否支援 DirectML (Windows AMD/Intel GPU 加速)
    """
    if sys.platform != "win32":
        return False
    try:
        import onnxruntime as ort
        return "DmlExecutionProvider" in ort.get_available_providers()
    except Exception:
        return False

@lru_cache(maxsize=1)
def get_device() -> str:
    """
    自動偵測最佳運算裝置
    優先級: CUDA -> DirectML -> CPU
    """
    # 1. 嘗試 CUDA
    cuda = _detect_cuda_via_torch() or _detect_cuda_via_ctranslate2()
    if cuda == "cuda" and is_cuda_runtime_available():
        return "cuda"
    
    # 2. 嘗試 DirectML (AMD/Intel)
    if has_directml():
        logger.info("Using DirectML for hardware acceleration")
        return "dml"

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

    ram_total, ram_available = _get_ram_info()
    os_name, os_version = _get_os_name()
    cpu_name, cpu_count = _get_cpu_info()
    info = {
        "device": device,
        "compute_type": compute_type,
        "device_name": "CPU",
        "memory_total": None,
        "memory_free": None,
        "has_nvidia_gpu": gpu_detected,
        "cuda_toolkit_installed": cuda_runtime,
        "driver_version": get_driver_version() if gpu_detected else None,
        "ram_total": ram_total,
        "ram_available": ram_available,
        "os_name": os_name,
        "os_version": os_version,
        "cpu_name": cpu_name,
        "cpu_count": cpu_count,
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


def _get_os_name() -> tuple[str, str]:
    """取得 OS 名稱與版本號（Windows 區分 10/11）"""
    import platform
    system = platform.system()
    if system == "Windows":
        try:
            build = int(platform.version().split(".")[-1])
            os_name = "Windows 11" if build >= 22000 else "Windows 10"
        except Exception:
            os_name = f"Windows {platform.release()}"
        return os_name, platform.version()
    if system == "Darwin":
        ver = platform.mac_ver()[0]
        return f"macOS {ver}", ver
    return f"{system} {platform.release()}", platform.version()


def _get_cpu_info() -> tuple[str, int | None]:
    """取得 CPU 名稱與邏輯核心數"""
    import platform
    import os as _os

    cpu_count = _os.cpu_count()

    if sys.platform == "win32":
        try:
            import winreg
            key = winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"HARDWARE\DESCRIPTION\System\CentralProcessor\0",
            )
            name, _ = winreg.QueryValueEx(key, "ProcessorNameString")
            winreg.CloseKey(key)
            if name:
                return name.strip(), cpu_count
        except Exception:
            pass

    if sys.platform == "darwin":
        try:
            import subprocess
            result = subprocess.run(
                ["sysctl", "-n", "machdep.cpu.brand_string"],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip(), cpu_count
        except Exception:
            pass

    try:
        with open("/proc/cpuinfo") as f:
            for line in f:
                if line.startswith("model name"):
                    name = line.split(":", 1)[1].strip()
                    if name:
                        return name, cpu_count
    except Exception:
        pass

    return platform.processor() or "Unknown CPU", cpu_count


def _get_ram_info() -> tuple[int | None, int | None]:
    """取得系統 RAM 資訊（bytes）"""
    try:
        import ctypes
        class MEMORYSTATUSEX(ctypes.Structure):
            _fields_ = [
                ("dwLength",                ctypes.c_ulong),
                ("dwMemoryLoad",            ctypes.c_ulong),
                ("ullTotalPhys",            ctypes.c_ulonglong),
                ("ullAvailPhys",            ctypes.c_ulonglong),
                ("ullTotalPageFile",        ctypes.c_ulonglong),
                ("ullAvailPageFile",        ctypes.c_ulonglong),
                ("ullTotalVirtual",         ctypes.c_ulonglong),
                ("ullAvailVirtual",         ctypes.c_ulonglong),
                ("sullAvailExtendedVirtual",ctypes.c_ulonglong),
            ]
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self.dwLength = ctypes.sizeof(self)
        stat = MEMORYSTATUSEX()
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat))
        return stat.ullTotalPhys, stat.ullAvailPhys
    except Exception:
        pass
    # fallback: /proc/meminfo (Linux)
    try:
        with open("/proc/meminfo") as f:
            lines = {k: int(v.split()[0]) * 1024
                     for k, _, v in (l.partition(":") for l in f)
                     if v.strip()}
        return lines.get("MemTotal"), lines.get("MemAvailable")
    except Exception:
        return None, None


def refresh_device_cache() -> None:
    """清除所有裝置偵測快取，強制重新偵測（CUDA DLL 下載後呼叫）"""
    global _device_info_cache
    _device_info_cache = None
    is_cuda_runtime_available.cache_clear()
    get_device.cache_clear()
    get_compute_type.cache_clear()
    has_nvidia_gpu.cache_clear()
    _get_gpu_name_via_smi.cache_clear()
    get_driver_version.cache_clear()
    logger.info("Device cache cleared, will re-detect on next call")


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


@lru_cache(maxsize=1)
def get_driver_version() -> str | None:
    """透過 nvidia-smi 取得 NVIDIA 驅動版本號，例如 '560.94'"""
    try:
        import subprocess
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=driver_version", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            version = result.stdout.strip().split("\n")[0].strip()
            if version:
                return version
    except Exception:
        pass
    return None


def select_torch_index() -> str:
    """
    根據 NVIDIA 驅動版本選擇對應的 PyTorch wheel 類型。

    對應規則（參見 BUILD_STRATEGY.md）：
      驅動 ≥ 560 → cu124
      驅動 ≥ 527 → cu121
      驅動 ≥ 452 → cu118
      無 GPU / 太舊 → cpu
    """
    if not has_nvidia_gpu():
        return "cpu"

    version_str = get_driver_version()
    if not version_str:
        return "cu124"  # fallback：有 GPU 但無法讀版本，用最新

    try:
        major = int(version_str.split(".")[0])
        if major >= 560:
            return "cu124"
        elif major >= 527:
            return "cu121"
        elif major >= 452:
            return "cu118"
        else:
            return "cpu"  # 驅動太舊，建議升級
    except (ValueError, IndexError):
        return "cu124"
