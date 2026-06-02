"""
GPU/CPU auto-detection module.
Automatically selects the optimal compute device and precision settings.
Supports CUDA detection via PyTorch or CTranslate2.
"""
import sys
import logging
from functools import lru_cache

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def is_cuda_runtime_available() -> bool:
    """
    Check whether CUDA runtime libraries (cublas, etc.) are available.

    Having an NVIDIA GPU does not guarantee CUDA compute capability;
    the CUDA Toolkit or corresponding DLLs must also be present.
    In PyInstaller-packaged builds the DLLs reside next to the exe
    and require additional search paths.
    """
    import ctypes
    import sys
    from pathlib import Path

    # 1. Standard search (system PATH, current directory, etc.)
    try:
        ctypes.CDLL("cublas64_12.dll")
        return True
    except (OSError, Exception):
        pass

    # 2. PyInstaller packaged environment: search in exe directory
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

    # 3. User-downloaded CUDA DLLs (%APPDATA%/MediaTranX/cuda/)
    # Load by absolute path to avoid unreliable PATH search in frozen environments
    try:
        import os
        appdata = os.environ.get('APPDATA', '')
        if appdata:
            cuda_dll = Path(appdata) / 'MediaTranX' / 'cuda' / 'cublas64_12.dll'
            if cuda_dll.exists():
                # Add directory via AddDllDirectory so dependent DLLs (cudart, etc.) can also be found
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
    """Attempt to detect CUDA via PyTorch."""
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
    """Attempt to detect CUDA via CTranslate2."""
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
    Detect whether DirectML is supported (Windows AMD/Intel GPU acceleration).
    """
    if sys.platform != "win32":
        return False
    try:
        import onnxruntime as ort
        return "DmlExecutionProvider" in ort.get_available_providers()
    except Exception:
        return False

def _cuda_can_run_kernels() -> bool:
    """True only if the GPU can actually launch a CUDA kernel with the installed
    torch build.

    A GPU can be *detected* (``torch.cuda.is_available()`` True) yet have no
    kernel image in the build for its compute capability — e.g. Kepler/K80
    (CC 3.7) under a cu12x build whose kernels target sm_50+. Every kernel launch
    then raises ``cudaErrorNoKernelImageForDevice`` at runtime. We test it once,
    empirically (a real kernel launch + sync), so callers fall back to CPU up
    front instead of every task crashing mid-run. This catches *any* "GPU
    detected but unusable" cause, not just an old architecture.

    Scope: this is a *torch* probe. When torch is a CUDA build, it also stands in
    for CTranslate2/Whisper, which share the same sm_50+ kernel floor (torch can't
    launch here => CTranslate2 can't either). But when torch is CPU-only and CUDA
    was detected via CTranslate2 instead, the probe can't speak to that path, so it
    must NOT veto — see the is_available() guard below.

    NOTE: a failed launch leaves the CUDA context in a sticky-error state; that's
    fine because callers abandon CUDA wholesale (device == "cpu") after this.
    """
    try:
        import torch
        if not torch.cuda.is_available():
            # torch is a CPU-only build. CUDA may still be usable via CTranslate2
            # (the caller detected it that way); this torch probe can't test it,
            # so don't downgrade — defer to the CTranslate2 detection result.
            return True
        # zeros() only allocates (no kernel); `+ 1` launches an elementwise
        # kernel; `.item()` syncs device->host so an async launch error surfaces.
        _ = (torch.zeros(1, device="cuda") + 1).item()
        return True
    except Exception as e:
        name = "GPU"
        try:
            import torch
            name = torch.cuda.get_device_name(0)
        except Exception:
            pass
        logger.warning(
            f"{name} cannot run CUDA kernels with the installed PyTorch build "
            f"({type(e).__name__}: {e}) — its compute capability is likely "
            f"unsupported by this CUDA build. Falling back to CPU."
        )
        return False


@lru_cache(maxsize=1)
def get_device() -> str:
    """
    Auto-detect the optimal compute device.
    Priority: CUDA -> DirectML -> CPU
    """
    # 1. Try CUDA — must be detected, have a loadable runtime, AND actually be
    #    able to launch a kernel (an old GPU can pass the first two yet have no
    #    kernel image for its arch -> cudaErrorNoKernelImageForDevice at runtime).
    cuda = _detect_cuda_via_torch() or _detect_cuda_via_ctranslate2()
    if cuda == "cuda" and is_cuda_runtime_available() and _cuda_can_run_kernels():
        return "cuda"
    
    # 2. Try DirectML (AMD/Intel)
    if has_directml():
        logger.info("Using DirectML for hardware acceleration")
        return "dml"

    # 3. Fallback to CPU
    if has_nvidia_gpu():
        logger.info("NVIDIA GPU detected but CUDA Toolkit not installed, falling back to CPU")
    else:
        logger.info("Using CPU (no GPU detected)")
    return "cpu"


def _supported_compute_types(device: str) -> set[str]:
    """
    Ask CTranslate2 which compute types the backend actually supports.

    This is authoritative: it reflects the GPU's compute capability. float16
    needs CC >= 7.0 (Volta+); older NVIDIA GPUs (Pascal/Maxwell) are detected
    as "cuda" but are NOT in the float16 set. Returns an empty set if
    CTranslate2 is unavailable, in which case callers keep legacy behaviour.
    """
    try:
        import ctranslate2

        return set(ctranslate2.get_supported_compute_types(device))
    except Exception:
        return set()


def compute_type_for(device: str) -> str:
    """
    Pick a CTranslate2 compute type the given device actually supports (uncached).

    Unlike get_compute_type(), the device is explicit — used when a wrapper
    locally downgrades cuda->cpu and must recompute the matching compute type.

    Returns:
        str: "float16"/"int8_float16"/"int8"/"float32" for cuda (whichever the
             backend supports), "int8" for cpu, "float32" for mps.
    """
    if device == "mps":
        return "float32"  # MPS currently works best with float32

    if device == "cuda":
        # float16 requires GPU compute capability >= 7.0. Older GPUs detect as
        # cuda but CTranslate2 rejects float16 ("does not support efficient
        # float16 computation"), so pick the best type the backend reports.
        supported = _supported_compute_types("cuda")
        for ct in ("float16", "int8_float16", "int8", "float32"):
            if ct in supported:
                return ct
        return "float16"  # CTranslate2 unavailable: preserve legacy default

    # CPU: int8 quantization to save memory (fall back to float32 if needed)
    supported = _supported_compute_types("cpu")
    for ct in ("int8", "float32"):
        if ct in supported:
            return ct
    return "int8"


@lru_cache(maxsize=1)
def get_compute_type() -> str:
    """Select the optimal precision for the auto-detected device (cached)."""
    return compute_type_for(get_device())


def _free_vram_via_torch() -> int | None:
    """Free VRAM (MB) via the torch CUDA runtime; None if unavailable."""
    try:
        import torch

        if not torch.cuda.is_available():
            return None
        torch.cuda.empty_cache()
        free_bytes, _ = torch.cuda.mem_get_info()
        return int(free_bytes // (1024 * 1024))
    except Exception:
        return None


def get_free_vram_mb() -> int | None:
    """
    Free GPU VRAM in MB. None means "unknown".

    Prefers nvidia-smi (whole-GPU view, matches what the llama-server subprocess
    will see, and works even when torch is a CPU-only build). Falls back to the
    torch CUDA runtime. Not cached — free VRAM is a live value.
    """
    try:
        import subprocess

        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.free",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            line = result.stdout.strip().split("\n")[0].strip()
            if line:
                return int(float(line))
    except Exception:
        pass
    return _free_vram_via_torch()


def fits_in_vram(required_mb: int, *, headroom_mb: int = 512) -> bool:
    """
    True if a model of `required_mb` fits in free VRAM (plus headroom).

    Unknown free VRAM (get_free_vram_mb() is None) returns True: we only
    downgrade when we can actually measure that it won't fit.
    """
    free = get_free_vram_mb()
    if free is None:
        return True
    return free >= required_mb + headroom_mb


_device_info_cache: dict | None = None


def get_device_info() -> dict:
    """
    Get complete device information (result is cached).

    Returns:
        dict: Contains device type, name, memory, and other info.
    """
    global _device_info_cache
    if _device_info_cache is not None:
        return _device_info_cache

    gpu_detected = has_nvidia_gpu()

    # Must call get_device() first (its internal torch import loads CUDA DLLs),
    # then call is_cuda_runtime_available(), otherwise @lru_cache caches wrong results
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
        "compute_capability": None,
        "memory_total": None,
        "memory_free": None,
        "torch_version": None,
        "torch_cuda_build": None,
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

    # Attempt to get detailed GPU info via PyTorch
    got_gpu_info = False
    try:
        import torch

        info["torch_version"] = torch.__version__
        info["torch_cuda_build"] = torch.version.cuda  # CUDA toolkit the wheel was built against
        if info["device"] == "cuda" and torch.cuda.is_available():
            info["device_name"] = torch.cuda.get_device_name(0)
            # Compute capability is authoritative for kernel-image compatibility:
            # an old GPU (e.g. K80 = 3.7) detects as cuda but a modern cu12x build
            # has no kernels for it -> cudaErrorNoKernelImageForDevice at runtime.
            cap = torch.cuda.get_device_capability(0)
            info["compute_capability"] = f"{cap[0]}.{cap[1]}"
            info["memory_total"] = torch.cuda.get_device_properties(0).total_memory
            info["memory_free"] = torch.cuda.memory_reserved(0) - torch.cuda.memory_allocated(0)
            got_gpu_info = True
        elif info["device"] == "mps":
            info["device_name"] = "Apple Silicon"
            got_gpu_info = True
    except Exception:
        pass

    # Fall back to nvidia-smi when PyTorch cannot get GPU info (not installed or CPU-only build)
    if gpu_detected and not got_gpu_info:
        info["device_name"] = _get_gpu_name_via_smi() or "NVIDIA GPU"

    # nvidia-smi fallback: when memory_total is still None and an NVIDIA GPU is present
    if info["memory_total"] is None and gpu_detected:
        try:
            import subprocess
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=memory.total,memory.free", "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0:
                parts = result.stdout.strip().split(",")
                info["memory_total"] = int(parts[0].strip()) * 1024 * 1024  # MB -> bytes
                info["memory_free"] = int(parts[1].strip()) * 1024 * 1024
        except Exception:
            pass

    _device_info_cache = info
    return info


def _get_os_name() -> tuple[str, str]:
    """Get OS name and version (distinguishes Windows 10/11)."""
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
    """Get CPU name and logical core count."""
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
    """Get system RAM info (in bytes)."""
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
    """Clear all device detection caches to force re-detection (call after CUDA DLL download)."""
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
    Detect whether an NVIDIA GPU is present via nvidia-smi (no torch dependency).

    Can detect GPU hardware even when torch is not installed or is CPU-only.
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
    """Get GPU name via nvidia-smi (result is cached)."""
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
    """Get NVIDIA driver version via nvidia-smi, e.g. '560.94'."""
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
    Select the PyTorch wheel variant based on NVIDIA driver version.

    Mapping rules (see BUILD_STRATEGY.md):
      Driver >= 560 -> cu124
      Driver >= 527 -> cu121
      Driver >= 452 -> cu118
      No GPU / too old -> cpu
    """
    if not has_nvidia_gpu():
        return "cpu"

    version_str = get_driver_version()
    if not version_str:
        return "cu124"  # fallback: GPU present but version unreadable, use latest

    try:
        major = int(version_str.split(".")[0])
        if major >= 560:
            return "cu124"
        elif major >= 527:
            return "cu121"
        elif major >= 452:
            return "cu118"
        else:
            return "cpu"  # driver too old, upgrade recommended
    except (ValueError, IndexError):
        return "cu124"
