"""Process-lifetime binding helpers (pure, no domain knowledge).

Windows: a per-instance Job Object with KILL_ON_JOB_CLOSE. When the owning
python process dies — including `taskkill /F` and hard crashes — the OS tears
down its handle table, closing the last job handle; with KILL_ON_JOB_CLOSE
the kernel kills the assigned child. No Python GC / __del__ / atexit is
involved (none of those run on `/F`). Retaining the job handle on the caller
only prevents a *premature* close while the child should still live.

POSIX (dev-only; the app is win32-primary): prctl(PR_SET_PDEATHSIG). Accepted
risk — PDEATHSIG fires on the spawning *thread's* death, not the process's;
not guaranteed correct across thread-pool recycling. Tolerated, dev-only.
"""
from __future__ import annotations

import ctypes
import logging
import sys
from typing import Callable, Optional

logger = logging.getLogger(__name__)

# winnt.h
JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x2000
# JOBOBJECTINFOCLASS::JobObjectExtendedLimitInformation
_JOB_EXTENDED_LIMIT_INFO_CLASS = 9

if sys.platform == "win32":
    class _BASIC_LIMIT_INFORMATION(ctypes.Structure):
        # 64-bit layout; ctypes applies natural alignment matching MSVC.
        _fields_ = [
            ("PerProcessUserTimeLimit", ctypes.c_int64),
            ("PerJobUserTimeLimit", ctypes.c_int64),
            ("LimitFlags", ctypes.c_uint32),
            ("MinimumWorkingSetSize", ctypes.c_size_t),
            ("MaximumWorkingSetSize", ctypes.c_size_t),
            ("ActiveProcessLimit", ctypes.c_uint32),
            ("Affinity", ctypes.c_size_t),  # ULONG_PTR
            ("PriorityClass", ctypes.c_uint32),
            ("SchedulingClass", ctypes.c_uint32),
        ]

    class _IO_COUNTERS(ctypes.Structure):
        _fields_ = [
            ("ReadOperationCount", ctypes.c_uint64),
            ("WriteOperationCount", ctypes.c_uint64),
            ("OtherOperationCount", ctypes.c_uint64),
            ("ReadTransferCount", ctypes.c_uint64),
            ("WriteTransferCount", ctypes.c_uint64),
            ("OtherTransferCount", ctypes.c_uint64),
        ]

    class _EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
        _fields_ = [
            ("BasicLimitInformation", _BASIC_LIMIT_INFORMATION),
            ("IoInfo", _IO_COUNTERS),
            ("ProcessMemoryLimit", ctypes.c_size_t),
            ("JobMemoryLimit", ctypes.c_size_t),
            ("PeakProcessMemoryUsed", ctypes.c_size_t),
            ("PeakJobMemoryUsed", ctypes.c_size_t),
        ]

    from ctypes import wintypes

    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    # WinDLL default restype is signed 32-bit (c_long) and untyped int args
    # marshal as c_int — that truncates/sign-extends 64-bit HANDLEs. Pin
    # restype/argtypes so handle values survive intact (the orphan-kill
    # mechanism depends on a correct job/process handle).
    _kernel32.CreateJobObjectW.restype = wintypes.HANDLE
    _kernel32.CreateJobObjectW.argtypes = [wintypes.LPVOID, wintypes.LPCWSTR]
    _kernel32.SetInformationJobObject.restype = wintypes.BOOL
    _kernel32.SetInformationJobObject.argtypes = [
        wintypes.HANDLE, ctypes.c_int, wintypes.LPVOID, wintypes.DWORD,
    ]
    _kernel32.AssignProcessToJobObject.restype = wintypes.BOOL
    _kernel32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    _kernel32.CloseHandle.restype = wintypes.BOOL
    _kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
else:  # pragma: no cover - exercised only on POSIX dev machines
    _EXTENDED_LIMIT_INFORMATION = None  # type: ignore[assignment]
    _kernel32 = None  # type: ignore[assignment]


def build_extended_limit_info() -> "_EXTENDED_LIMIT_INFORMATION":
    """Win32 only: extended-limit struct with KILL_ON_JOB_CLOSE set."""
    info = _EXTENDED_LIMIT_INFORMATION()
    info.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    return info


def create_kill_on_close_job() -> Optional[int]:
    """Create + configure a KILL_ON_JOB_CLOSE Job Object.

    Returns the job handle (int) or ``None`` on any failure (logged). Never
    raises — the safety net must never block llama-server from starting.
    """
    if _kernel32 is None:
        return None
    try:
        job = _kernel32.CreateJobObjectW(None, None)
        if not job:
            logger.warning(
                "CreateJobObjectW failed (err=%s); llama-server will start "
                "without OS lifetime binding",
                ctypes.get_last_error(),
            )
            return None
        info = build_extended_limit_info()
        ok = _kernel32.SetInformationJobObject(
            job, _JOB_EXTENDED_LIMIT_INFO_CLASS,
            ctypes.byref(info), ctypes.sizeof(info),
        )
        if not ok:
            logger.warning(
                "SetInformationJobObject failed (err=%s); discarding job",
                ctypes.get_last_error(),
            )
            close_job(job)
            return None
        return int(job)
    except Exception as e:  # noqa: BLE001 - safety net must not raise
        logger.warning("Job Object creation errored: %s", e)
        return None


def assign_process_to_job(job: int, process_handle: int) -> bool:
    """Assign an OS process handle (int) to ``job``. False on failure (logged)."""
    if _kernel32 is None:
        return False
    try:
        ok = _kernel32.AssignProcessToJobObject(job, process_handle)
        if not ok:
            logger.warning(
                "AssignProcessToJobObject failed (err=%s); orphan-kill not "
                "armed for this server",
                ctypes.get_last_error(),
            )
            return False
        return True
    except Exception as e:  # noqa: BLE001
        logger.warning("AssignProcessToJobObject errored: %s", e)
        return False


def close_job(job: int) -> None:
    """Close a job handle. Best-effort; swallows errors."""
    if _kernel32 is None:
        return
    try:
        _kernel32.CloseHandle(job)
    except Exception as e:  # noqa: BLE001
        logger.warning("CloseHandle(job) errored: %s", e)


def posix_pdeathsig_preexec() -> Optional[Callable[[], None]]:
    """Return a Popen ``preexec_fn`` that arms PR_SET_PDEATHSIG=SIGKILL.

    ``None`` on win32 (Popen requires preexec_fn=None there). Dev-only;
    thread-recycle caveat documented in the module docstring / spec.
    """
    if sys.platform == "win32":
        return None

    def _set_pdeathsig() -> None:  # pragma: no cover - POSIX dev only
        import signal
        libc = ctypes.CDLL("libc.so.6", use_errno=True)
        PR_SET_PDEATHSIG = 1
        libc.prctl(PR_SET_PDEATHSIG, signal.SIGKILL)

    return _set_pdeathsig
