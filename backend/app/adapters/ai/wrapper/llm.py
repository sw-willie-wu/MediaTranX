"""LlmWrapper - BaseWrapper wrapper around a LlamaServer binary adapter.

Knows GGUF / VLM registry structure, builds startup config, handles
thinking-tag stripping. Delegates subprocess + HTTP to LlamaServer.
"""
from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any, Callable, Optional

from .base import BaseWrapper
from app.adapters.binary.llama_server import LlamaServer

logger = logging.getLogger(__name__)


class LlmWrapper(BaseWrapper):
    """BaseWrapper subclass for GGUF/VLM models via llama-server.

    Composition: holds a `LlamaServer` instance as `self._model` (set by
    `_load_impl`). Chat/complete forward through the server and strip
    Qwen3 <think> blocks.
    """

    def _load_impl(
        self,
        model_path: Path,
        config: dict,
        on_progress: Optional[Callable[[float, str], None]] = None,
    ) -> Any:
        from app.adapters.device import has_nvidia_gpu

        n_gpu_layers = config.get("layers", 99) if has_nvidia_gpu() else 0
        n_ctx = config.get("n_ctx", 4096)
        mmproj_path = config.get("mmproj_path")

        server = LlamaServer()
        server.start(
            model_path=model_path,
            n_ctx=n_ctx,
            n_gpu_layers=n_gpu_layers,
            mmproj_path=mmproj_path,
            on_progress=on_progress,
        )
        return server  # becomes self._model

    def _unload_impl(self) -> None:
        if self._model is not None:
            self._model.stop()

    def chat(
        self,
        messages: list[dict],
        max_tokens: int = 2048,
        temperature: float = 0.1,
        top_k: int = 40,
        top_p: float = 0.9,
        stop: Optional[list[str]] = None,
    ) -> str:
        """Chat completion with thinking-tag stripping."""
        if self._model is None:
            raise RuntimeError("LlmWrapper not loaded; call acquire() first")
        content = self._model.post_chat(
            messages=messages, max_tokens=max_tokens,
            temperature=temperature, top_k=top_k, top_p=top_p, stop=stop,
        )
        return self._strip_thinking(content)

    def complete(
        self,
        prompt: str,
        max_tokens: int = 2048,
        temperature: float = 0.1,
        top_k: int = 40,
        top_p: float = 0.9,
        stop: Optional[list[str]] = None,
    ) -> str:
        """Raw completion with thinking-tag stripping."""
        if self._model is None:
            raise RuntimeError("LlmWrapper not loaded; call acquire() first")
        content = self._model.post_completion(
            prompt=prompt, max_tokens=max_tokens,
            temperature=temperature, top_k=top_k, top_p=top_p, stop=stop,
        )
        return self._strip_thinking(content)

    def kill_process(self) -> None:
        """Best-effort cancellation hook for fake_progress(cancellable=...).

        No-op if the model is not loaded or the subprocess handle is gone.
        """
        if self._model is None:
            return
        proc = getattr(self._model, "_process", None)
        if proc is None:
            return
        try:
            proc.kill()
        except Exception:
            pass

    @staticmethod
    def _strip_thinking(text: str) -> str:
        """Remove <think>...</think> blocks from Qwen3 thinking mode output."""
        return re.sub(r'<think>[\s\S]*?</think>\s*', '', text).strip()

    def _resolve_model_path(self, model_id: str, variant, manager):
        from app.adapters.ai.registry import FORMAT_GGUF, MODELS_REGISTRY

        if model_id in MODELS_REGISTRY.get(FORMAT_GGUF, {}):
            return self._resolve_gguf_path(model_id, variant, manager)
        raise ValueError(f"Unknown model for LlmWrapper: {model_id}")

    def _resolve_gguf_path(self, model_id: str, variant: Optional[str], manager):
        from app.adapters.ai.registry import FORMAT_GGUF, MODELS_REGISTRY

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

        model_path = manager.get_model_path(model_id, f"{size}:{quant}")
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
