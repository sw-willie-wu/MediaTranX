"""
Startup system/hardware/driver diagnostic logging.

Emits one consolidated block at startup so a tester's app.log is self-describing
(OS, CPU/RAM, GPU + compute capability, driver, torch CUDA build) without us
having to ask. Compute capability + torch CUDA build are the fields that explain
GPU failures like cudaErrorNoKernelImageForDevice (an old GPU whose arch isn't in
the installed CUDA build) or float16-unsupported.

Every field is independently guarded: a missing AI environment (no torch), a
missing GPU, or any detection failure must NEVER raise — we log what we can.
"""
import logging
import os
import platform
from importlib import metadata

logger = logging.getLogger(__name__)


def app_version() -> str:
    """Best-effort app version. Electron passes MEDIATRANX_APP_VERSION; fall back
    to package metadata, then 'unknown'."""
    v = os.environ.get("MEDIATRANX_APP_VERSION")
    if v:
        return v
    try:
        return metadata.version("mediatranx-backend")
    except Exception:
        return "unknown"


def _gb(n) -> str:
    try:
        return f"{n / 1024 ** 3:.1f} GB"
    except Exception:
        return "?"


def _collect_device_lines() -> list[str]:
    """GPU/device 相關欄位；單獨包一層方便測試與 guard。"""
    lines: list[str] = []
    from app.adapters.device import get_device_info
    info = get_device_info()

    lines.append(f"CPU:      {info.get('cpu_name')} / {info.get('cpu_count')} cores")
    if info.get("ram_total"):
        lines.append(f"RAM:      {_gb(info['ram_total'])}")
    lines.append(
        f"Device:   {info.get('device')} (compute_type={info.get('compute_type')})"
    )
    if info.get("has_nvidia_gpu"):
        lines.append(f"GPU:      {info.get('device_name')}")
        if info.get("compute_capability"):
            lines.append(f"  Compute capability: {info['compute_capability']}")
        if info.get("memory_total"):
            lines.append(f"  VRAM: {_gb(info['memory_total'])}")
        if info.get("driver_version"):
            lines.append(f"  Driver: {info['driver_version']}")
    if info.get("torch_version"):
        cuda_build = info.get("torch_cuda_build") or "none / CPU build"
        lines.append(f"Torch:    {info['torch_version']} (CUDA build {cuda_build})")
    else:
        lines.append("Torch:    not available (AI environment not installed yet)")
    return lines


def collect_env_summary(settings) -> str:
    """收集環境摘要為多行字串。每欄位獨立 guard、永不 raise。

    開機 log 與問題回報共用同一份真相。
    """
    lines: list[str] = []
    try:
        lines.append(f"OS:       {platform.platform()}")
        lines.append(f"Python:   {platform.python_version()}")
    except Exception:
        pass
    try:
        lines.extend(_collect_device_lines())
    except Exception as e:
        lines.append(f"Device info unavailable: {e}")
    try:
        lines.append(f"DataRoot: {settings.path.root}")
    except Exception:
        pass
    return "\n".join(lines)


def log_system_info(settings) -> None:
    """Log a consolidated system/hardware/driver block. Best-effort, never raises."""
    lines = ["=== System Info ==="]

    try:
        mode = "frozen" if getattr(settings, "is_frozen", False) else "dev"
        lines.append(f"App:      MediaTranX {app_version()} ({mode})")
    except Exception:
        pass

    try:
        lines.append(collect_env_summary(settings))
    except Exception:
        pass

    lines.append("===================")
    logger.info("\n".join(lines))
