"""
LlamaServerRuntime - llama-server subprocess executor.
Replaces GGUFRuntime; supports text LLM and vision language models (VLM) via HTTP API.
"""
import json
import logging
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable, Optional

from .base import BaseRuntime

logger = logging.getLogger(__name__)

LLAMA_SERVER_STARTUP_TIMEOUT = 120  # seconds


def _find_free_port(start: int = 18080, end: int = 18200) -> int:
    for port in range(start, end):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("127.0.0.1", port)) != 0:
                return port
    raise RuntimeError("No available port found for llama-server")


class LlamaServerRuntime(BaseRuntime):
    """
    llama-server subprocess executor.

    _load_model_impl() starts a llama-server subprocess and waits until ready.
    acquire() yields self so callers can invoke self.chat() directly.
    _unload_model_impl() terminates the subprocess.

    FORMAT_GGUF supports both text LLM and vision language models (VLM).
    Vision models carry mmproj_path in config; --mmproj is added at startup automatically.
    """

    def __init__(self, slot: str):
        super().__init__(slot)
        self._process: Optional[subprocess.Popen] = None
        self._port: Optional[int] = None
        self._log_file = None

    # ─────────────────────────────────────────────
    # BaseRuntime interface implementation
    # ─────────────────────────────────────────────

    def _load_model_impl(
        self,
        model_path: Path,
        config: dict,
        on_progress: Optional[Callable[[float, str], None]] = None,
    ) -> Any:
        from app.engine.device import has_nvidia_gpu
        from app.init.configs import SETTINGS

        if on_progress:
            on_progress(0.05, "task.progress.preparing_llama")

        # Locate llama-server executable
        llama_dir = SETTINGS.path.llama
        exe_name = "llama-server.exe" if sys.platform == "win32" else "llama-server"
        server_exe = llama_dir / exe_name
        if not server_exe.exists():
            raise FileNotFoundError(
                f"llama-server not found: {server_exe}\n"
                "Please go to Settings and re-install the AI core."
            )

        self._port = _find_free_port()
        n_gpu_layers = config.get("layers", 99) if has_nvidia_gpu() else 0
        n_ctx = config.get("n_ctx", 4096)

        cmd = [
            str(server_exe),
            "--model", str(model_path.resolve()),
            "--port", str(self._port),
            "--host", "127.0.0.1",
            "--ctx-size", str(n_ctx),
            "--n-gpu-layers", str(n_gpu_layers),
            "--reasoning", "off",
        ]

        mmproj_path = config.get("mmproj_path")
        if mmproj_path:
            cmd += ["--mmproj", str(Path(mmproj_path).resolve())]

        logger.info(
            f"Starting llama-server on port {self._port} "
            f"(model={Path(str(model_path)).name}, n_gpu_layers={n_gpu_layers})"
        )

        if on_progress:
            on_progress(0.2, f"task.progress.starting_llama|{self._port}")

        base = SETTINGS.path.data
        log_dir = base / "logs" if SETTINGS.is_frozen else base
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

        return self  # acquire() yields self so callers can invoke chat()

    def _unload_model_impl(self) -> None:
        if self._process is not None:
            logger.info(f"Terminating llama-server (port {self._port})")
            try:
                self._process.terminate()
                self._process.wait(timeout=10)
            except Exception as e:
                logger.warning(f"Error terminating llama-server: {e}")
                try:
                    self._process.kill()
                except Exception:
                    pass
            self._process = None
            self._port = None
        if self._log_file is not None:
            try:
                self._log_file.close()
            except Exception:
                pass
            self._log_file = None

    def _resolve_model_path(self, model_id: str, variant: Optional[str] = None):
        from app.engine.ai.registry import FORMAT_GGUF, MODELS_REGISTRY

        if model_id in MODELS_REGISTRY.get(FORMAT_GGUF, {}):
            return self._resolve_gguf_path(model_id, variant)
        raise ValueError(f"Unknown model for LlamaServerRuntime: {model_id}")

    # ─────────────────────────────────────────────
    # Inference API
    # ─────────────────────────────────────────────

    def chat(
        self,
        messages: list[dict],
        max_tokens: int = 2048,
        temperature: float = 0.1,
        top_k: int = 40,
        top_p: float = 0.9,
        stop: Optional[list[str]] = None,
    ) -> str:
        """
        Call llama-server /v1/chat/completions.

        Returns:
            The model response text (stripped).
        """
        import urllib.error
        import urllib.request

        if not self._port:
            raise RuntimeError("llama-server not started; call acquire() first")

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
            with urllib.request.urlopen(req, timeout=300) as resp:
                result = json.loads(resp.read())
                content = result["choices"][0]["message"]["content"].strip()
                # Strip Qwen3 thinking tags if present
                content = self._strip_thinking(content)
                return content
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"llama-server API error {e.code}: {body}")

    @staticmethod
    def _strip_thinking(text: str) -> str:
        """Remove <think>...</think> blocks from Qwen3 thinking mode output."""
        import re
        return re.sub(r'<think>[\s\S]*?</think>\s*', '', text).strip()

    def complete(
        self,
        prompt: str,
        max_tokens: int = 2048,
        temperature: float = 0.1,
        top_k: int = 40,
        top_p: float = 0.9,
        stop: list[str] | None = None,
    ) -> str:
        """
        Raw text completion (no chat template).
        Uses /completion endpoint instead of /v1/chat/completions.
        """
        import urllib.error
        import urllib.request

        if not self._port:
            raise RuntimeError("llama-server not started; call acquire() first")

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
            with urllib.request.urlopen(req, timeout=300) as resp:
                result = json.loads(resp.read())
            content = result.get("content", "").strip()
            return self._strip_thinking(content)
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"llama-server API error {e.code}: {body}")

    # ─────────────────────────────────────────────
    # Internal path resolution
    # ─────────────────────────────────────────────

    def _resolve_gguf_path(self, model_id: str, variant: Optional[str]):
        from app.engine.ai.registry import FORMAT_GGUF, MODELS_REGISTRY

        family = MODELS_REGISTRY[FORMAT_GGUF][model_id]

        if ":" in (variant or ""):
            size, quant = variant.split(":", 1)
        else:
            size = variant
            quant = family["default_variant"].get(size)
            if not quant:
                raise ValueError(f"No default quantization for {model_id}/{size}")

        specs = family["specs"].get(size)
        if not specs:
            raise ValueError(f"Unknown size '{size}' for {model_id}")

        variant_spec = specs["variants"].get(quant)
        if not variant_spec:
            raise ValueError(f"Unknown quantization '{quant}' for {model_id}/{size}")

        model_path = self._manager.get_model_path(model_id, f"{size}:{quant}")
        if not model_path:
            raise FileNotFoundError(
                f"Model not downloaded: {model_id}/{size}/{quant}. "
                "Please download it from AI Module Management first."
            )

        config = {
            "model_id": model_id,
            "size": size,
            "quantization": quant,
            "layers": specs["layers"],
            "n_ctx": specs.get("n_ctx_default", specs.get("n_ctx", 4096)),
        }

        # Handle mmproj for vision models
        if "mmproj_filename" in variant_spec:
            from app.init.configs import SETTINGS
            base_dir = (SETTINGS.path.models / model_id).resolve()
            mmproj_path = base_dir / variant_spec["mmproj_filename"]
            if not mmproj_path.exists():
                raise FileNotFoundError(
                    f"mmproj not downloaded: {model_id}/{size}/{quant}. "
                    "Please download it from AI Module Management first."
                )
            config["mmproj_path"] = mmproj_path

        return model_path, config

    # ─────────────────────────────────────────────
    # Internal utilities
    # ─────────────────────────────────────────────

    def _wait_ready(
        self,
        on_progress: Optional[Callable] = None,
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
