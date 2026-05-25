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


class LocalChatSession:
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

    def _guard(self, pct: Optional[float] = None, msg: Optional[str] = None):
        """Single-poller cancel watcher. Per-call (pct, msg) override the
        session defaults set at __init__. Either-None means "use default".

        Required by the VLM frame-pick loop pattern: one open session
        across many per-item calls, each item carries its own cancel_pct
        and cancel_msg for monotonic progress reporting and i18n labels.
        See spec §F3 step 1.
        """
        if self._on_progress is None:
            return nullcontext()
        return cancel_guard(
            self._on_progress, cancellable=self,
            progress=pct if pct is not None else self._cancel_pct,
            message=msg if msg is not None else self._cancel_msg,
        )

    def chat(
        self,
        messages: list[dict],
        *,
        max_tokens: int,
        temperature: float,
        top_k: int = 40,
        top_p: float = 0.9,
        stop: Optional[list[str]] = None,
        cancel_pct: Optional[float] = None,        # per-call override
        cancel_msg: Optional[str] = None,          # per-call override
    ) -> str:
        with self._guard(cancel_pct, cancel_msg):
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
        cancel_pct: Optional[float] = None,
        cancel_msg: Optional[str] = None,
    ) -> str:
        with self._guard(cancel_pct, cancel_msg):
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
        cancel_pct: Optional[float] = None,
        cancel_msg: Optional[str] = None,
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
        with self._guard(cancel_pct, cancel_msg):
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
        model_family: Optional[str] = None,           # MODIFIED: was required
        model_size: Optional[str] = None,             # MODIFIED: was required
        quantization: Optional[str] = None,
        remote_provider=None,                         # NEW
        remote_model: Optional[str] = None,           # NEW
        on_load_progress: Optional[Callable] = None,
        on_progress: Optional[Callable] = None,
        cancel_pct: float = 0.0,
        cancel_msg: str = "task.progress.generating",
    ) -> Iterator:
        """Hold an LLM loaded (local) OR open a remote-provider session
        for the duration of the block.

        Dispatch is determined by `remote_provider`:
        - remote_provider is not None → yield RemoteChatSession (no local
          model acquire). `remote_model` is required.
        - remote_provider is None → yield LocalChatSession via
          llama_runtime.acquire(). `model_family` + `model_size` are
          required (legacy invariant).

        See spec core/.claude/specs/2026-05-25-video-summary-remote-line.md
        §F3.
        """
        if remote_provider is not None:
            if not remote_model:
                raise ValueError(
                    "ChatService.session(remote_provider=...) requires a "
                    "non-empty remote_model"
                )
            # Lazy import — avoids a startup-time cycle and keeps
            # _remote_chat off the cold-start path for local-only users.
            from app.services._remote_chat import RemoteChatSession
            yield RemoteChatSession(
                remote_provider, remote_model,
                on_progress=on_progress,
                cancel_pct=cancel_pct, cancel_msg=cancel_msg,
            )
            return

        # Local path
        if not model_family or not model_size:
            raise ValueError(
                "ChatService.session() requires either remote_provider+remote_model "
                "or both model_family and model_size"
            )
        variant = f"{model_size}:{quantization}" if quantization else model_size
        with self._llama_runtime.acquire(
            model_family, variant, on_progress=on_load_progress,
        ):
            yield LocalChatSession(self._llama_runtime, on_progress=on_progress,
                                   cancel_pct=cancel_pct, cancel_msg=cancel_msg)

    def chat(
        self,
        prompt: str,
        model_family: str = "gemma4",
        model_size: str = "8b",
        max_tokens: int = 4096,
        temperature: float = 0.1,
        *,
        remote_provider=None,                         # NEW
        remote_model: Optional[str] = None,           # NEW
        on_progress: Optional[Callable] = None,
        cancel_pct: float = 0.0,
        cancel_msg: str = "task.progress.generating",
    ) -> str:
        """One-shot chat (backward-compat). Opens its own session for the
        single call. When remote_provider is supplied the local model
        defaults are inert (dispatch short-circuits to remote).
        """
        with self.session(
            model_family=model_family, model_size=model_size,
            remote_provider=remote_provider, remote_model=remote_model,
            on_progress=on_progress, cancel_pct=cancel_pct,
            cancel_msg=cancel_msg,
        ) as session:
            return session.chat(
                messages=[{"role": "user", "content": prompt}],
                max_tokens=max_tokens, temperature=temperature,
            )

    def chat_with_images(
        self,
        prompt: str,
        images: list[Path | str],
        *,
        model_family: Optional[str] = None,
        model_size: Optional[str] = None,
        quantization: Optional[str] = None,
        max_tokens: int,
        temperature: float,
        remote_provider=None,                         # NEW
        remote_model: Optional[str] = None,           # NEW
        on_progress: Optional[Callable] = None,
        cancel_pct: float = 0.0,
        cancel_msg: str = "task.progress.generating",
    ) -> str:
        """One-shot VLM chat. Backward-compat shape; opens a session
        per call. Supports local OR remote dispatch via the same
        ChatService.session() rules."""
        with self.session(
            model_family=model_family, model_size=model_size,
            quantization=quantization,
            remote_provider=remote_provider, remote_model=remote_model,
            on_progress=on_progress, cancel_pct=cancel_pct,
            cancel_msg=cancel_msg,
        ) as session:
            return session.chat_with_images(
                prompt=prompt, images=images,
                max_tokens=max_tokens, temperature=temperature,
            )


# Backward-compat alias — keeps existing
# `from app.services.llm.chat_service import ChatSession` imports working.
# Used by pipeline/ocr.py:18, document/translate_service/text.py:17,
# tests/services/test_chat_service_cancel.py. Deprecated; remove after
# follow-up A refactor (project_unified_capabilities).
ChatSession = LocalChatSession
