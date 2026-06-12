"""One-shot CLI sidecar runner for Vulkan/Metal model binaries.

For run-once CLIs (ncnn-vulkan upscalers, rife-ncnn-vulkan, demucs-rs): spawn,
stream merged stdout+stderr to an optional line callback, wait, raise
SidecarError on non-zero exit / hard crash / timeout. The child is bound to a
KILL_ON_JOB_CLOSE Job Object (Windows) so it dies with the backend — the same
orphan-kill mechanism LlamaServer uses. Distinct from the persistent-HTTP
LlamaServer; both live in adapters/binary/, and a persistent variant can be
added beside this one without changing callers (spec C5: spawn-per-task is a
call-site choice, not hardcoded architecture).
"""
from __future__ import annotations

import logging
import subprocess
import sys
import threading
from pathlib import Path
from typing import Callable, Optional, Sequence

from app.adapters.binary import _proc_lifetime

logger = logging.getLogger(__name__)


def _no_window() -> dict:
    """Suppress the console window flash on Windows (same idiom as ytdlp)."""
    if sys.platform == "win32":
        return {"creationflags": subprocess.CREATE_NO_WINDOW}
    return {}


class SidecarError(RuntimeError):
    """Sidecar CLI failed (non-zero exit, NTSTATUS hard crash, or timeout).
    Carries the exit code, hard-crash flag (GPU-incompat signature, decoded
    like LlamaServerCrashError), and the newest lines of the merged output."""

    def __init__(self, exe: str, code: int, tail: str):
        self.code = code
        is_hard, reason = _proc_lifetime.classify_exit_code(code)
        self.is_hard_crash = is_hard
        self.tail = tail  # full captured tail (message keeps the newest 300 chars)
        super().__init__(f"{Path(exe).name} failed ({reason}): {tail[-300:]}")


class CliSidecar:
    """Run a one-shot CLI binary with orphan-kill binding + output streaming."""

    def __init__(self, exe: str, on_line: Optional[Callable[[str], None]] = None,
                 cwd: Optional[str] = None):
        self.exe = exe
        self._on_line = on_line
        self._cwd = cwd

    def run(self, args: Sequence[str], timeout: Optional[float] = None) -> int:
        # Merge stderr INTO stdout and pump the single stream: draining only one
        # of two PIPEs can deadlock proc.wait() when the child fills the other
        # buffer — ncnn writes progress to stderr, demucs-rs to stdout, so both
        # must be captured; merging is the simplest deadlock-free way. Explicit
        # utf-8 + replace: bare text=True would decode with the locale codepage
        # (cp950 on zh-TW Windows) and a stray UTF-8 byte would kill the pump.
        proc = subprocess.Popen(
            [self.exe, *args],
            stdin=subprocess.DEVNULL,  # a one-shot CLI must never block on a prompt
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            encoding="utf-8", errors="replace", bufsize=1,
            cwd=self._cwd,
            preexec_fn=_proc_lifetime.posix_pdeathsig_preexec(),
            **_no_window(),
        )
        logger.debug(f"sidecar spawned: {Path(self.exe).name} (pid={proc.pid})")

        # Bind AFTER a successful spawn (llama_server order) so a missing exe
        # cannot leak a job handle; close immediately if assignment fails.
        job = _proc_lifetime.create_kill_on_close_job()
        if job is not None:
            if not _proc_lifetime.assign_process_to_job(
                job, int(proc._handle)  # noqa: SLF001 - same as llama_server
            ):
                _proc_lifetime.close_job(job)
                job = None

        tail: list[str] = []

        def _pump() -> None:
            assert proc.stdout is not None
            for line in proc.stdout:
                line = line.rstrip("\n")
                tail.append(line)
                if len(tail) > 50:
                    tail.pop(0)
                if self._on_line:
                    try:
                        self._on_line(line)
                    except Exception:
                        # A progress-parser bug must not kill the drain: a dead
                        # pump lets the child fill the pipe and deadlock wait().
                        logger.exception("sidecar on_line callback failed; draining continues")

        t = threading.Thread(target=_pump, daemon=True)
        t.start()
        try:
            proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            # Deterministic kill + reap on every platform: the Windows job-close
            # kill is only a safety net, and POSIX has no job at all.
            proc.kill()
            try:
                # Capped: a GPU-wedged child (driver stuck in kernel mode) can
                # survive TerminateProcess; never block the caller forever.
                proc.wait(timeout=5.0)
            except subprocess.TimeoutExpired:
                logger.warning(f"sidecar {Path(self.exe).name} survived kill; "
                               f"abandoning (Windows job close is the safety net)")
            t.join(timeout=1.0)  # flush the pump before snapshotting the tail
            # Timeout marker is APPENDED: the message slices tail[-300:], so a
            # prepended marker would be the first thing truncated away.
            raise SidecarError(
                self.exe, -1, "\n".join(tail) + f"\ntimeout after {timeout}s"
            ) from None
        finally:
            t.join(timeout=1.0)
            if job is not None:
                _proc_lifetime.close_job(job)
        if proc.returncode != 0:
            raise SidecarError(self.exe, proc.returncode, "\n".join(tail))
        return proc.returncode
