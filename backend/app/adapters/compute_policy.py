"""Higher-level compute-device policy: composes device detection + VRAM fit into
a per-task device choice, pushing user notices on downgrade, and classifies raw
GPU exceptions into friendly error codes (for the OFF path)."""
from app.adapters import device
from app.utils.task_notices import push_task_notice


def resolve_device_for_task(required_vram_mb: int = 0, *, model_id: str | None = None) -> str:
    """Pick the device for a task, honouring the CPU-fallback policy.

    - Global downgrade (kernel/driver/runtime): surface a one-shot session notice.
    - Per-task VRAM shortfall (only when fallback allowed): downgrade + notice.
    - Fallback OFF: never VRAM-check; return whatever get_device() gave.
    """
    base = device.get_device()
    if base != "cuda":
        reason = device.get_global_downgrade_reason()
        if reason and not device.is_global_downgrade_reported():
            push_task_notice(reason)
            device.mark_global_downgrade_reported()
        return base

    if (
        device.is_cpu_fallback_allowed()
        and required_vram_mb > 0
        and not device.fits_in_vram(required_vram_mb)
    ):
        push_task_notice("vram_insufficient", model=model_id)
        return "cpu"
    return base


def classify_gpu_error(exc: BaseException) -> str | None:
    """Best-effort map of a raw GPU exception to a compute error code."""
    msg = str(exc).lower()
    if "no kernel image" in msg or "nokernelimage" in msg:
        return "gpu_unsupported"
    if "out of memory" in msg or "alloc_failed" in msg or "alloc failed" in msg:
        return "vram_insufficient"
    return None
