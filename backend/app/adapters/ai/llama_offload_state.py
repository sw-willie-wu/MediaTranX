"""Sticky per-install record of whether llama-server GPU offload hard-crashes
on this machine's GPU.

Once a hard crash (0xC0000005) is observed during GPU offload we record it so
subsequent cold starts skip GPU up front instead of crashing once each time.
Auto-invalidates when the GPU name or the bundled llama-server binary changes
(swap card / re-install AI core with a different CUDA build)."""
from __future__ import annotations

import logging
import sys

from app.db.dao.app_setting_dao import AppSettingDAO

logger = logging.getLogger(__name__)

_KEY = "gpu.llama_offload"


def _current_signature() -> dict:
    """(gpu_name, llama-server.exe size:mtime) — the invalidation key."""
    from app.adapters.device import get_device_info
    from app.init.configs import SETTINGS

    gpu = (get_device_info() or {}).get("device_name", "unknown")
    exe = SETTINGS.path.llama / (
        "llama-server.exe" if sys.platform == "win32" else "llama-server"
    )
    try:
        st = exe.stat()
        build = f"{st.st_size}:{int(st.st_mtime)}"
    except OSError:
        build = "unknown"
    return {"gpu": gpu, "build": build}


def llama_offload_known_broken() -> bool:
    """True only if a prior hard crash was recorded AND the GPU + llama build
    still match. A mismatch is treated as 'unknown' (cleared) so a new card or
    a re-installed binary gets a fresh GPU attempt."""
    row = AppSettingDAO().get(_KEY)
    if not row or not row.get("unusable"):
        return False
    sig = _current_signature()
    if row.get("gpu") == sig["gpu"] and row.get("build") == sig["build"]:
        return True
    AppSettingDAO().set(_KEY, {"unusable": False})  # stale → re-probe
    return False


def mark_llama_offload_broken() -> None:
    sig = _current_signature()
    AppSettingDAO().set(_KEY, {"unusable": True, **sig})
    logger.info("Recorded llama GPU offload as unusable on this machine (%s)", sig)
