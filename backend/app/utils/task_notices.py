"""Per-task user notices (e.g. GPU→CPU downgrade), surfaced via task polling.

A notice is a {"code": str, "params": dict} dict. Producers (device/compute
policy, deep in a worker thread) call push_task_notice(); the worker binds the
current task's notices list to a ContextVar around handler execution. Reads from
the polling (async) thread must snapshot under the same lock.
"""
import contextvars
import threading
from typing import Optional

_current_task_notices: contextvars.ContextVar[Optional[list]] = contextvars.ContextVar(
    "current_task_notices", default=None
)
_lock = threading.Lock()


def push_task_notice(code: str, **params) -> None:
    """Append a notice to the current task's sink (no-op if none bound)."""
    sink = _current_task_notices.get()
    if sink is None:
        return
    clean = {k: v for k, v in params.items() if v is not None}
    with _lock:
        sink.append({"code": code, "params": clean})


def snapshot_notices(sink: list) -> list:
    """Thread-safe shallow copy for serialization on the reader thread."""
    with _lock:
        return list(sink)
