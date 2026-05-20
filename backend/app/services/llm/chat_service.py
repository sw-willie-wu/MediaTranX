"""LLM chat service — typed façade over LlmWrapper.

ChatService.session() opens an acquire() block on the underlying LlmWrapper
and yields a ChatSession with chat / complete / chat_with_images methods
that reuse the loaded model.
"""
from __future__ import annotations

import base64
import logging
from contextlib import contextmanager, nullcontext
from pathlib import Path
from typing import Callable, Iterator, Optional

from app.utils.inference import cancel_guard

logger = logging.getLogger(__name__)


class ChatSession:
    """Bound to a single LlmWrapper.acquire() block.

    Methods reuse the loaded model — caller does NOT need to reload between
    calls (no per-batch acquire cost).
    """

    def __init__(self, llama_runtime, *, on_progress=None,
                 cancel_pct: float = 0.0,
                 cancel_msg: str = "task.progress.generating"):
        self._runtime = llama_runtime
        self._on_progress = on_progress
        self._cancel_pct = cancel_pct
        self._cancel_msg = cancel_msg

    def _guard(self):
        """Single poll+kill watcher for the wrapped blocking call.

        nullcontext when no on_progress (legacy behaviour); otherwise
        cancel_guard, which itself passes through if an enclosing
        fake_progress(cancellable=) already owns poll+kill (shared ContextVar)
        — exactly one watcher per call.
        """
        if self._on_progress is None:
            return nullcontext()
        return cancel_guard(self._on_progress, cancellable=self,
                            progress=self._cancel_pct, message=self._cancel_msg)

    def chat(
        self,
        messages: list[dict],
        *,
        max_tokens: int,
        temperature: float,
        top_k: int = 40,
        top_p: float = 0.9,
        stop: Optional[list[str]] = None,
    ) -> str:
        with self._guard():
            return self._runtime.chat(
                messages=messages, max_tokens=max_tokens, temperature=temperature,
                top_k=top_k, top_p=top_p, stop=stop,
            )

    def complete(
        self,
        prompt: str,
        *,
        max_tokens: int,
        temperature: float,
        top_k: int = 40,
        top_p: float = 0.9,
        stop: Optional[list[str]] = None,
    ) -> str:
        with self._guard():
            return self._runtime.complete(
                prompt=prompt, max_tokens=max_tokens, temperature=temperature,
                top_k=top_k, top_p=top_p, stop=stop,
            )

    def chat_with_images(
        self,
        prompt: str,
        images: list[Path | str],
        *,
        max_tokens: int,
        temperature: float,
        top_k: int = 40,
        top_p: float = 0.9,
    ) -> str:
        """Send a prompt + images to the loaded VLM via OpenAI-compat multimodal messages.

        Encodes each image as a `data:<mime>;base64,<b64>` URI (the format
        llama-server's /v1/chat/completions accepts when mmproj is loaded).
        """
        content: list[dict] = [{"type": "text", "text": prompt}]
        for img_path in images:
            p = Path(img_path)
            mime, b64 = _read_image_as_data_uri(p)
            content.append({
                "type": "image_url",
                "image_url": {"url": f"data:{mime};base64,{b64}"},
            })
        messages = [{"role": "user", "content": content}]
        with self._guard():
            return self._runtime.chat(
                messages=messages, max_tokens=max_tokens, temperature=temperature,
                top_k=top_k, top_p=top_p, stop=None,
            )

    def kill_process(self) -> None:
        """Best-effort cancellation: stop the underlying llama-server.

        Routes through LlamaServer.stop(timeout=2) (consistent _process/_job
        state, immediate Windows terminate unblocks the HTTP call). Used by
        `fake_progress(cancellable=...)`. No-op if the runtime isn't loaded
        yet; never raises.
        """
        model = getattr(self._runtime, "_model", None)
        if model is None:
            return
        try:
            model.stop(timeout=2.0)
        except Exception:
            pass  # best-effort


def _read_image_as_data_uri(path: Path) -> tuple[str, str]:
    """Return (mime, base64) for an image on disk."""
    suffix = path.suffix.lower().lstrip(".")
    mime = {
        "png": "image/png",
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "webp": "image/webp",
        "gif": "image/gif",
    }.get(suffix, "image/png")
    b64 = base64.b64encode(path.read_bytes()).decode("ascii")
    return mime, b64


class ChatService:
    """Single LLM entry point.

    Use `session()` for multi-call workflows (translation batches, OCR loops).
    Use `chat()` for one-shot fire-and-forget.
    """

    def __init__(self, llama_runtime):
        self._llama_runtime = llama_runtime
        logger.info("ChatService initialized")

    @contextmanager
    def session(
        self,
        *,
        model_family: str,
        model_size: str,
        quantization: Optional[str] = None,
        on_load_progress: Optional[Callable] = None,
        on_progress: Optional[Callable] = None,
        cancel_pct: float = 0.0,
        cancel_msg: str = "task.progress.generating",
    ) -> Iterator[ChatSession]:
        """Hold an LLM loaded for the duration of the block.

        Inside the `with`, call session.chat / .complete / .chat_with_images
        repeatedly without reloading the model.

        Maps `model_family` → ModelManager's `model_id` and
        `f"{model_size}:{quantization}"` → `variant` (LlmWrapper._resolve_model_path
        parses the colon to split size + quant). Plain `model_size` (no `:`)
        when quantization is None — `_resolve_gguf_path` picks the default
        quant from the registry's `default_variant` table.
        """
        variant = f"{model_size}:{quantization}" if quantization else model_size
        with self._llama_runtime.acquire(
            model_family, variant, on_progress=on_load_progress,
        ):
            yield ChatSession(self._llama_runtime, on_progress=on_progress,
                              cancel_pct=cancel_pct, cancel_msg=cancel_msg)

    def chat(
        self,
        prompt: str,
        model_family: str = "gemma4",
        model_size: str = "8b",
        max_tokens: int = 4096,
        temperature: float = 0.1,
        *,
        on_progress: Optional[Callable] = None,
        cancel_pct: float = 0.0,
        cancel_msg: str = "task.progress.generating",
    ) -> str:
        """One-shot chat (backward-compat). Opens its own session for the single call."""
        with self.session(model_family=model_family, model_size=model_size,
                          on_progress=on_progress, cancel_pct=cancel_pct,
                          cancel_msg=cancel_msg) as session:
            return session.chat(
                messages=[{"role": "user", "content": prompt}],
                max_tokens=max_tokens, temperature=temperature,
            )

    def chat_with_images(
        self,
        prompt: str,
        images: list[Path | str],
        *,
        model_family: str,
        model_size: str,
        quantization: Optional[str] = None,
        max_tokens: int,
        temperature: float,
        on_progress: Optional[Callable] = None,
        cancel_pct: float = 0.0,
        cancel_msg: str = "task.progress.generating",
    ) -> str:
        """One-shot VLM chat. Backward-compat shape for callers that don't need a session."""
        with self.session(
            model_family=model_family, model_size=model_size, quantization=quantization,
            on_progress=on_progress, cancel_pct=cancel_pct, cancel_msg=cancel_msg,
        ) as session:
            return session.chat_with_images(
                prompt=prompt, images=images,
                max_tokens=max_tokens, temperature=temperature,
            )
