"""LlamaServer - pure llama-server binary subprocess adapter.

Zero registry / zero VRAM-slot / zero domain knowledge. Owned by
LlmWrapper (app/engine/ai/runtime/llm.py) via composition.
"""
from __future__ import annotations

import json
import logging
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Callable, Optional, TextIO

logger = logging.getLogger(__name__)

LLAMA_SERVER_STARTUP_TIMEOUT = 180  # seconds (normal load 10-20s; buffer for cold cache / VRAM pressure)


def _find_free_port(start: int = 18080, end: int = 18200) -> int:
    for port in range(start, end):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("127.0.0.1", port)) != 0:
                return port
    raise RuntimeError("No available port found for llama-server")


class LlamaServer:
    """Pure llama-server subprocess + HTTP adapter.

    Lifecycle:
        server = LlamaServer()
        server.start(model_path, n_ctx=4096, n_gpu_layers=99)
        text = server.post_chat(messages=[...])
        server.stop()
    """

    def __init__(self) -> None:
        self._process: Optional[subprocess.Popen] = None
        self._port: Optional[int] = None
        self._log_file: Optional[TextIO] = None
        self._job: Optional[int] = None  # Win32 Job Object handle (F1)

    @property
    def port(self) -> Optional[int]:
        return self._port

    def is_running(self) -> bool:
        return self._process is not None and self._process.poll() is None

    def start(
        self,
        model_path: Path,
        n_ctx: int,
        n_gpu_layers: int,
        mmproj_path: Optional[Path] = None,
        on_progress: Optional[Callable[[float, str], None]] = None,
    ) -> None:
        """Start llama-server subprocess and block until /health returns ok."""
        from app.init.configs import SETTINGS

        if on_progress:
            on_progress(0.05, "task.progress.preparing_llama")

        llama_dir = SETTINGS.path.llama
        exe_name = "llama-server.exe" if sys.platform == "win32" else "llama-server"
        server_exe = llama_dir / exe_name
        if not server_exe.exists():
            raise FileNotFoundError(
                f"llama-server not found: {server_exe}\n"
                "Please go to Settings and re-install the AI core."
            )

        self._port = _find_free_port()

        cmd = [
            str(server_exe),
            "--model", str(model_path.resolve()),
            "--port", str(self._port),
            "--host", "127.0.0.1",
            "--ctx-size", str(n_ctx),
            "--n-gpu-layers", str(n_gpu_layers),
            "--reasoning", "off",
        ]
        if mmproj_path:
            cmd += ["--mmproj", str(Path(mmproj_path).resolve())]

        logger.info(
            f"Starting llama-server on port {self._port} "
            f"(model={Path(str(model_path)).name}, n_gpu_layers={n_gpu_layers})"
        )
        if on_progress:
            on_progress(0.2, f"task.progress.starting_llama|{self._port}")

        log_dir = SETTINGS.path.log
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / "llama_server.log"
        self._log_file = open(str(log_path), "a", encoding="utf-8")  # noqa: SIM115

        self._process = subprocess.Popen(
            cmd,
            stdout=self._log_file,
            stderr=self._log_file,
            cwd=str(llama_dir),
        )

        self._wait_ready(on_progress)

        logger.info(f"llama-server ready on port {self._port}")
        if on_progress:
            on_progress(1.0, "task.progress.model_loaded")

    def stop(self, timeout: float = 10.0) -> None:
        """Stop the subprocess deterministically and close the job handle.

        terminate() → wait(timeout); on timeout/exception escalate to kill().
        State (`_process`/`_port`/`_job`) is cleared **only after the child is
        confirmed gone** (`poll()` is not None). If both terminate and kill
        fail the handle is retained so a later stop() can retry — we never
        pretend a live child is gone.
        """
        proc = self._process
        if proc is not None:
            logger.info(f"Terminating llama-server (port {self._port})")
            try:
                proc.terminate()
                proc.wait(timeout=timeout)
            except Exception as e:
                logger.warning(f"terminate() failed, escalating to kill(): {e}")
                try:
                    proc.kill()
                    proc.wait(timeout=timeout)
                except Exception as e2:
                    logger.error(f"kill() also failed; retaining handle: {e2}")
            if proc.poll() is not None:
                self._process = None
                self._port = None
                self._close_job()
            else:
                logger.error(
                    f"llama-server (port {self._port}) survived stop(); "
                    "handle retained for a later retry"
                )
        if self._log_file is not None:
            try:
                self._log_file.close()
            except Exception:
                pass
            self._log_file = None

    def _close_job(self) -> None:
        """Close the Win32 Job Object handle (deterministic; prevents
        per-model-switch kernel-handle accumulation over a long session)."""
        if self._job is not None:
            from app.adapters.binary import _proc_lifetime
            _proc_lifetime.close_job(self._job)
            self._job = None

    def post_chat(
        self,
        messages: list[dict],
        max_tokens: int = 2048,
        temperature: float = 0.1,
        top_k: int = 40,
        top_p: float = 0.9,
        stop: Optional[list[str]] = None,
    ) -> str:
        """POST /v1/chat/completions → content str (whitespace-trimmed, no tag stripping)."""
        import urllib.error
        import urllib.request

        if not self._port:
            raise RuntimeError("LlamaServer not started; call start() first")

        payload: dict = {
            "model": "local",
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "top_k": top_k,
            "top_p": top_p,
            "repeat_penalty": 1.1,
        }
        if stop:
            payload["stop"] = stop

        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"http://127.0.0.1:{self._port}/v1/chat/completions",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=900) as resp:
                result = json.loads(resp.read())
                return result["choices"][0]["message"]["content"].strip()
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"llama-server API error {e.code}: {body}")

    def post_completion(
        self,
        prompt: str,
        max_tokens: int = 2048,
        temperature: float = 0.1,
        top_k: int = 40,
        top_p: float = 0.9,
        stop: Optional[list[str]] = None,
    ) -> str:
        """POST /completion → content str (whitespace-trimmed, no tag stripping)."""
        import urllib.error
        import urllib.request

        if not self._port:
            raise RuntimeError("LlamaServer not started; call start() first")

        payload: dict = {
            "prompt": prompt,
            "n_predict": max_tokens,
            "temperature": temperature,
            "top_k": top_k,
            "top_p": top_p,
            "repeat_penalty": 1.1,
        }
        if stop:
            payload["stop"] = stop

        url = f"http://127.0.0.1:{self._port}/completion"
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url, data=data, headers={"Content-Type": "application/json"}
        )

        try:
            with urllib.request.urlopen(req, timeout=900) as resp:
                result = json.loads(resp.read())
            return result.get("content", "").strip()
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"llama-server API error {e.code}: {body}")

    def _wait_ready(
        self,
        on_progress: Optional[Callable[[float, str], None]] = None,
        timeout: int = LLAMA_SERVER_STARTUP_TIMEOUT,
    ) -> None:
        import urllib.error
        import urllib.request

        deadline = time.time() + timeout
        step = 0
        while time.time() < deadline:
            if self._process and self._process.poll() is not None:
                raise RuntimeError(
                    f"llama-server exited unexpectedly (code {self._process.returncode})"
                )
            try:
                url = f"http://127.0.0.1:{self._port}/health"
                with urllib.request.urlopen(url, timeout=2) as resp:
                    data = json.loads(resp.read())
                    if data.get("status") == "ok":
                        return
            except (urllib.error.URLError, OSError, json.JSONDecodeError):
                pass

            step += 1
            if on_progress and step % 10 == 0:
                elapsed = step * 0.5
                on_progress(
                    0.2 + min(elapsed / timeout, 0.7) * 0.7,
                    f"task.progress.waiting_model_load|{elapsed:.0f}",
                )
            time.sleep(0.5)

        raise TimeoutError(f"llama-server startup timed out ({timeout}s)")
