"""LLM chat service — typed façade over LlmWrapper.

ChatService.session() opens an acquire() block on the underlying LlmWrapper
and yields a ChatSession with chat / complete / chat_with_images methods
that reuse the loaded model.
"""
from __future__ import annotations

import asyncio
import base64
import logging
import threading
from contextlib import contextmanager, nullcontext
from pathlib import Path
from typing import AsyncIterator, Callable, Iterator, Optional

from app.utils.inference import cancel_guard

logger = logging.getLogger(__name__)


def _parse_openai_compat_chunk(
    raw_chunk: dict,
    id_by_index: dict[int, str] | None = None,
) -> list[dict]:
    """Parse one OpenAI chat completions SSE chunk into 0..N typed events.

    A single chunk can produce:
    - 0 events: empty choices (e.g. usage-only final chunk) or finish_reason chunks
    - 1 'delta' event: text content delta
    - 1+ 'tool_call' events: one per tool_call delta in the chunk

    Returns:
        List of dicts matching the stream() yield types:
        - {'type': 'delta', 'message_id': str, 'text': str}
        - {'type': 'tool_call', 'id': str, 'name': str,
           'parent_message_id': str, 'args_delta': str}

    Notes:
    - message_id comes from chunk['id'] (OpenAI assigns per response).
    - tool_call.id is only present on the FIRST chunk for a given tool call;
      later chunks identify by `index` only (no `id` key).  Caller passes a
      mutable `id_by_index` dict (per-stream state) so we can substitute the
      remembered real id into every subsequent chunk; without this, the
      frontend SSE accumulator would store `args` deltas under the empty id
      `""` while the UI tool-call card (keyed by the real id) shows empty
      args (production bug observed live with gpt-4o-mini agent path).
    """
    out: list[dict] = []
    chunk_id = raw_chunk.get("id", "")
    choices = raw_chunk.get("choices", [])
    if not choices:
        return out
    delta = choices[0].get("delta", {})

    # Text content delta
    if delta.get("content"):
        out.append({
            "type": "delta",
            "message_id": chunk_id,
            "text": delta["content"],
        })

    # Tool call deltas (0..N per chunk)
    for tc_delta in delta.get("tool_calls", []):
        tc_index = tc_delta.get("index")
        tc_id = tc_delta.get("id", "")
        # Carry id across chunks via id_by_index map (Phase 1 agent fix).
        if id_by_index is not None and tc_index is not None:
            if tc_id:
                id_by_index[tc_index] = tc_id
            elif tc_index in id_by_index:
                tc_id = id_by_index[tc_index]
        out.append({
            "type": "tool_call",
            "id": tc_id,
            "name": tc_delta.get("function", {}).get("name", ""),
            "parent_message_id": chunk_id,
            "args_delta": tc_delta.get("function", {}).get("arguments", ""),
        })

    return out


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
        self._stream_kill_pending: bool = False  # race flag for stream() producer

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
        task: Optional[str] = None,                # accepted for symmetry; local path ignores
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
        task: Optional[str] = None,                # accepted for symmetry; local path ignores
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
        task: Optional[str] = None,                # accepted for symmetry; local path ignores
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

    async def stream(
        self,
        messages: list[dict],
        *,
        tools: list[dict] | None = None,
        max_tokens: int,
        temperature: float,
    ) -> AsyncIterator[dict]:
        """Yield dicts from the LLM stream via a producer-thread + asyncio.Queue bridge.

        Yields one of:
        - {'type': 'delta', 'message_id': str, 'text': str}
        - {'type': 'tool_call', 'id': str, 'name': str,
           'parent_message_id': str, 'args_delta': str}
        - {'type': 'done', 'usage': {'prompt_tokens': int, 'completion_tokens': int}}

        Cancel-pass-through mode (spec §5.3.2 / §9): does NOT install its own
        cancel_guard watcher.  The calling AgentService (Task 1.4) owns the
        cancel hook via session.kill_process().  on_progress=None for the
        agent path; cancel_guard auto-resolves to nullcontext per _guard().

        Race protection: _stream_kill_pending is reset to False at the top of
        each call so sequential streams don't carry stale state.  The producer
        thread checks the flag immediately after stream start (and again after
        the first urlopen returns) — mirrors remote_chat.py:67-84 pattern.
        """
        loop = asyncio.get_running_loop()
        q: asyncio.Queue = asyncio.Queue(maxsize=64)
        SENTINEL_END = object()
        SENTINEL_ERR = object()
        # Reset per-call so a prior kill doesn't block the next stream()
        self._stream_kill_pending = False

        def producer() -> None:
            try:
                if self._stream_kill_pending:
                    raise OSError("cancel_pre_stream: killed before producer started")
                stream_iter = self._runtime.chat_stream(
                    messages=messages,
                    tools=tools,
                    max_tokens=max_tokens,
                    temperature=temperature,
                )
                # Re-check race AFTER urlopen returns (m12)
                if self._stream_kill_pending:
                    raise OSError("cancel_pre_first_chunk")

                # B3 fix: capture usage IN-LOOP.  With stream_options.include_usage=true,
                # the OpenAI-compat last data chunk (before [DONE]) carries `usage` at
                # the top level — it does NOT contain a `choices` delta.  Skip it from
                # delta yield, store the usage block.
                usage: dict | None = None
                # See RemoteChatSession.stream for why this map is needed —
                # OpenAI sends the real tool_call.id only on the first chunk
                # of each call; later chunks identify by `index` only.
                id_by_index: dict[int, str] = {}
                for raw_chunk in stream_iter:
                    if raw_chunk.get("usage"):
                        usage = raw_chunk["usage"]
                        # Don't `continue` — usage chunk in OpenAI SSE has empty choices,
                        # so _parse_openai_compat_chunk produces nothing.  Safe to fall through.
                    parsed = _parse_openai_compat_chunk(raw_chunk, id_by_index)
                    for p in parsed:
                        # Use run_coroutine_threadsafe + blocking put() for backpressure:
                        # put_nowait raises QueueFull inside the event-loop callback (the
                        # producer thread can't catch it), silently dropping tokens when the
                        # consumer is slow.  put() waits instead of dropping.
                        asyncio.run_coroutine_threadsafe(q.put(p), loop).result()
                asyncio.run_coroutine_threadsafe(
                    q.put({"type": "done", "usage": usage}), loop
                ).result()
                asyncio.run_coroutine_threadsafe(q.put(SENTINEL_END), loop).result()
            except Exception as exc:
                try:
                    asyncio.run_coroutine_threadsafe(
                        q.put((SENTINEL_ERR, exc)), loop
                    ).result(timeout=5.0)
                except Exception:
                    pass  # loop shut down or queue abandoned — consumer already gone

        threading.Thread(target=producer, daemon=True, name="llm-stream-producer").start()

        sentinel_end_reached = False
        try:
            while True:
                item = await q.get()
                if item is SENTINEL_END:
                    sentinel_end_reached = True
                    return
                if isinstance(item, tuple) and item[0] is SENTINEL_ERR:
                    raise item[1]
                # A "done" chunk means the producer iterated to natural EOF
                # (it's emitted just before SENTINEL_END — see producer above).
                # Flag now so a caller that breaks immediately after `done`
                # (AgentService.run does this on the multi-round path) won't
                # trip the finally's spurious kill_process() — that kill clears
                # LlamaServer._port but leaves LlmWrapper._model dangling,
                # which makes is_loaded() lie and the next acquire skip the
                # re-start, breaking every multi-round agent conversation.
                if isinstance(item, dict) and item.get("type") == "done":
                    sentinel_end_reached = True
                yield item
        finally:
            # Generator-cleanup contract: if consumer abandons (async for ... break,
            # task cancellation, exception), kill_process() closes the HTTP socket
            # so the producer thread exits promptly instead of leaking until natural
            # stream completion.  Idempotent: safe to call twice (e.g. from
            # AgentService.run's cancel hook AND here).
            #
            # WARM-POOL SAFETY: do NOT kill on clean SENTINEL_END exit.  If we
            # called kill_process() here unconditionally, LlamaServer.stop() would
            # clear _process/_port while LlmWrapper._model still references the
            # (now-dead) server.  wrapper.is_loaded() would return True (lying),
            # so the next ChatService.session() → mm.acquire() → _ensure_runtime
            # would see needs_reload=False and yield a broken runtime whose very
            # next .stream()/.chat() call raises
            # RuntimeError("LlamaServer not started; call start() first").
            # Result: every multi-turn agent conversation breaks on round 2.
            if not sentinel_end_reached:
                self.kill_process()

    def kill_process(self) -> None:
        """Best-effort cancellation: stop the underlying llama-server.

        Routes through LlamaServer.stop(timeout=2) (consistent _process/_job
        state, immediate Windows terminate unblocks the HTTP call). Used by
        `fake_progress(cancellable=...)`. No-op if the runtime isn't loaded
        yet; never raises.

        Additionally for stream() callers: sets _stream_kill_pending so a
        not-yet-started producer thread's race check will raise immediately.

        After the subprocess stop, also clear the wrapper's `_model` ref so
        `wrapper.is_loaded()` tells the truth on the next acquire — otherwise
        a stale ref points at a dead LlamaServer, the next mm.acquire skips
        the re-start, and the very next chat_stream raises "LlamaServer not
        started". This recovery is critical for the agent path which calls
        kill_process on producer exceptions (HTTP 500, parse errors, etc.).
        """
        self._stream_kill_pending = True   # race flag for stream() producer
        model = getattr(self._runtime, "_model", None)
        if model is None:
            return
        try:
            model.stop(timeout=2.0)
        except Exception:
            pass  # best-effort
        # Clear wrapper ref so is_loaded() stops lying; idempotent.
        try:
            self._runtime._model = None
        except Exception:
            pass


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
            # remote_chat off the cold-start path for local-only users.
            from app.services.llm.remote_chat import RemoteChatSession
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
