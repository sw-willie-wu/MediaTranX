"""LlmWrapper - BaseWrapper wrapper around a LlamaServer binary adapter.

Knows GGUF / VLM registry structure, builds startup config, handles
thinking-tag stripping. Delegates subprocess + HTTP to LlamaServer.
"""
from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any, Callable, Iterator, Optional

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
        if self._model is not None:
            try:
                self._model.stop()
            except Exception as e:
                logger.warning(
                    f"Failed to stop prior llama-server before reload: {e}"
                )

        from app.adapters.compute_policy import resolve_device_for_task
        from app.adapters import device as device_mod
        from app.adapters.ai.llama_offload_state import (
            llama_offload_known_broken,
            mark_llama_offload_broken,
        )
        from app.utils.task_notices import push_task_notice
        from app.adapters.binary.llama_server import LlamaServerCrashError

        required_vram = config.get("required_vram_mb", 0)
        model_id = config.get("model_id")
        # Compatibility-aware device choice (kernel probe + VRAM + fallback policy),
        # shared with Whisper/PyTorch. llama uses GPU only for "cuda" (not dml/cpu).
        device_choice = resolve_device_for_task(required_vram, model_id=model_id)
        use_gpu = device_choice == "cuda"
        if use_gpu:
            # Only hit the sticky-state DB when we'd actually use the GPU. A DB
            # hiccup must not abort an otherwise-working load — degrade to
            # "attempt GPU" (the reactive net below still catches a real crash).
            try:
                if llama_offload_known_broken():
                    use_gpu = False
            except Exception:
                logger.warning(
                    "llama_offload_state unavailable; attempting GPU offload anyway",
                    exc_info=True,
                )
        n_gpu_layers = config.get("layers", 99) if use_gpu else 0
        n_ctx = config.get("n_ctx", 4096)
        mmproj_path = config.get("mmproj_path")

        server = LlamaServer()

        def _do_start(ngl: int) -> None:
            server.start(
                model_path=model_path,
                n_ctx=n_ctx,
                n_gpu_layers=ngl,
                mmproj_path=mmproj_path,
                on_progress=on_progress,
            )

        try:
            _do_start(n_gpu_layers)
        except LlamaServerCrashError as e:
            # Reactive safety net: torch's kernel probe is a strong but imperfect
            # proxy for llama's separate CUDA build. If GPU offload still hard-
            # crashes (0xC0000005) and fallback is allowed, record + retry on CPU.
            if n_gpu_layers > 0 and e.is_hard_crash and device_mod.is_cpu_fallback_allowed():
                logger.warning(
                    "llama-server hard-crashed on GPU offload (%s); "
                    "marking GPU offload unusable and retrying on CPU",
                    e.reason,
                )
                mark_llama_offload_broken()
                push_task_notice("gpu_unsupported", model=model_id)
                server.stop()  # clear the dead process + old log handle before
                #                the clean CPU restart (avoids a misleading
                #                "existing llama-server" warning from start())
                _do_start(0)
            else:
                raise
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

    def chat_stream(
        self,
        messages: list[dict],
        *,
        tools: list[dict] | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.1,
    ) -> Iterator[dict]:
        """Streaming chat completion — raw OpenAI-compat SSE chunks.

        Thin proxy to LlamaServer.chat_stream(); parsing of delta/tool_call
        semantics and cancel coordination live in ChatService.stream().
        Used by the agent path (LocalChatSession.stream → ChatService producer
        thread → this method).
        """
        if self._model is None:
            raise RuntimeError("LlmWrapper not loaded; call acquire() first")
        return self._model.chat_stream(
            messages=messages,
            tools=tools,
            max_tokens=max_tokens,
            temperature=temperature,
        )

    def kill_process(self) -> None:
        """Best-effort cancellation hook for fake_progress(cancellable=...).

        Routes through LlamaServer.stop(timeout=2): terminate() is immediate
        on Windows so the in-flight HTTP call unblocks at once; the bounded
        wait keeps `_process`/`_job` state consistent. No-op if not loaded;
        never raises.
        """
        if self._model is None:
            return
        try:
            self._model.stop(timeout=2.0)
        except Exception:
            pass  # best-effort

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
            "required_vram_mb": manager.get_vram_requirement(model_id, f"{size}:{quant}"),
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
