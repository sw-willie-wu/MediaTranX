"""RemoteChatSession — cancellable, per-call-cancel-overridable session over
a RemoteProvider.

Symmetric with LocalChatSession (services/llm/chat_service.py):
identical public surface (chat / complete / chat_with_images /
kill_process). `complete` is intentionally unimplemented for remote
providers in this phase (spec §F2 / R6).

Cancellation:
- The single-poller `cancel_guard` mechanism (utils/inference.py)
  wraps each blocking call inside _guard().
- The blocking call is `provider.chat(..., abort_hook=self._set_current)`
  (or chat_with_images). The provider invokes abort_hook(resp) right
  after urlopen returns so we can stash the response object.
- The watcher's `kill_process()` (called from another thread when the
  task is cancelled) closes the stashed response → reader's socket
  recv raises OSError → cancel_guard.finally re-raises the stored
  TaskCancelledError, replacing the OSError via Python's
  exception-during-finally semantics.
- Race protection (pre-connection): `_kill_pending` is set by
  kill_process when no response is stashed yet. _set_current checks
  the flag on each call; if set, it closes the response immediately
  and raises OSError so the provider's read loop never starts.

Spec: core/.claude/specs/2026-05-25-video-summary-remote-line.md §F2.
"""
from __future__ import annotations

import asyncio
import threading
from contextlib import nullcontext
from typing import AsyncIterator, Callable, Optional, Protocol

from app.utils.inference import cancel_guard


class _Closable(Protocol):
    def close(self) -> None: ...


class RemoteChatSession:
    """Cancellable session wrapper around a RemoteProvider + model id."""

    def __init__(
        self, prov, model: str, *,
        on_progress: Optional[Callable] = None,
        cancel_pct: float = 0.0,
        cancel_msg: str = "task.progress.generating",
    ):
        self._prov = prov
        self._model = model
        self._on_progress = on_progress
        self._cancel_pct = cancel_pct
        self._cancel_msg = cancel_msg
        self._current_response: Optional[_Closable] = None
        self._kill_pending: bool = False         # set by kill_process before resp ready
        self._stream_kill_pending: bool = False  # race flag for stream() producer

    def _guard(self, pct: Optional[float] = None, msg: Optional[str] = None):
        """Per-call override of session-default cancel_pct/cancel_msg.
        Returns nullcontext when no on_progress (no cancel watcher needed)."""
        if self._on_progress is None:
            return nullcontext()
        return cancel_guard(
            self._on_progress, cancellable=self,
            progress=pct if pct is not None else self._cancel_pct,
            message=msg if msg is not None else self._cancel_msg,
        )

    def _set_current(self, resp: _Closable) -> None:
        """abort_hook: invoked by the provider exactly once, immediately
        after urlopen returns. Stashes the response so kill_process()
        can close it across threads.

        Race fix (spec MINOR-V4-4): assign first, then check
        _kill_pending. If a single-fire cancel watcher's kill_process
        landed before we got here, _kill_pending=True; we close resp
        ourselves and raise so the provider's read loop never starts.
        """
        self._current_response = resp
        if self._kill_pending:
            try:
                resp.close()
            except Exception:
                pass
            self._current_response = None
            raise OSError("cancel_pre_response: response closed before read")

    def chat(
        self,
        messages: list[dict],
        *,
        max_tokens: int,
        temperature: float,
        top_k: int = 40,
        top_p: float = 0.9,
        stop: Optional[list[str]] = None,
        cancel_pct: Optional[float] = None,         # per-call override
        cancel_msg: Optional[str] = None,
        task: Optional[str] = None,
    ) -> str:
        with self._guard(cancel_pct, cancel_msg):
            try:
                return self._prov.chat(
                    model=self._model, messages=messages,
                    max_tokens=max_tokens, temperature=temperature,
                    abort_hook=self._set_current, task=task,
                )
            finally:
                self._current_response = None

    def complete(self, *args, **kwargs) -> str:
        raise NotImplementedError(
            "RemoteChatSession.complete() is intentionally unimplemented "
            "(no caller in current app/; see spec §Out-of-scope follow-up #5)."
        )

    def chat_with_images(
        self,
        prompt: str,
        images: list,
        *,
        max_tokens: int,
        temperature: float,
        top_k: int = 40,
        top_p: float = 0.9,
        cancel_pct: Optional[float] = None,
        cancel_msg: Optional[str] = None,
        task: Optional[str] = None,
    ) -> str:
        with self._guard(cancel_pct, cancel_msg):
            try:
                return self._prov.chat_with_images(
                    model=self._model, prompt=prompt, images=images,
                    max_tokens=max_tokens, temperature=temperature,
                    abort_hook=self._set_current, task=task,
                )
            finally:
                self._current_response = None

    async def stream(
        self,
        messages: list[dict],
        *,
        tools: list[dict] | None = None,
        max_tokens: int,
        temperature: float,
    ) -> AsyncIterator[dict]:
        """Async generator — producer thread + asyncio.Queue bridge.

        Mirrors LocalChatSession.stream (chat_service.py Task 1.3) exactly.

        Yields one of:
        - {'type': 'delta', 'message_id': str, 'text': str}
        - {'type': 'tool_call', 'id': str, 'name': str,
           'parent_message_id': str, 'args_delta': str}
        - {'type': 'done', 'usage': dict | None}

        Routing:
        - Providers that expose chat_completions_stream() → Chat Completions path
          (OpenAI: Task 4.5; Ollama: Task 4.7).
        - Providers lacking that method → raises NotImplementedError
          (Gemini — streaming tool-calling deferred to Wave 4.6).

        Cancel-pass-through: does NOT install its own cancel_guard.  The
        calling AgentService owns the cancel hook via kill_process().
        """
        from app.services.llm.chat_service import _parse_openai_compat_chunk

        if not hasattr(self._prov, "chat_completions_stream"):
            raise NotImplementedError(
                f"{type(self._prov).__name__} does not yet implement "
                "chat_completions_stream(); use an OpenAI or Ollama model "
                "for the agent (Gemini streaming tool-calling is Wave 4.6)."
            )

        loop = asyncio.get_running_loop()
        q: asyncio.Queue = asyncio.Queue(maxsize=64)
        SENTINEL_END = object()
        SENTINEL_ERR = object()
        # Reset per-call so a prior kill doesn't stall the next stream()
        self._stream_kill_pending = False

        def producer() -> None:
            try:
                if self._stream_kill_pending:
                    raise OSError("cancel_pre_stream: killed before producer started")
                stream_iter = self._prov.chat_completions_stream(
                    model=self._model,
                    messages=messages,
                    tools=tools,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    abort_hook=self._set_current,
                )
                if self._stream_kill_pending:
                    raise OSError("cancel_pre_first_chunk")

                usage: dict | None = None
                # Track tool-call id per index across chunks: OpenAI puts the
                # real id only on the first chunk of each call.  Without this
                # map, the AG-UI SSE accumulator on the frontend keys args
                # deltas by `id=""` while the UI tool-call card uses the real
                # id — args land in the wrong bucket and the card shows `{}`.
                id_by_index: dict[int, str] = {}
                for raw_chunk in stream_iter:
                    if raw_chunk.get("usage"):
                        usage = raw_chunk["usage"]
                    parsed = _parse_openai_compat_chunk(raw_chunk, id_by_index)
                    for p in parsed:
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
                    pass  # loop shut down or queue abandoned

        threading.Thread(
            target=producer, daemon=True, name="remote-stream-producer"
        ).start()

        sentinel_end_reached = False
        try:
            while True:
                item = await q.get()
                if item is SENTINEL_END:
                    sentinel_end_reached = True
                    return
                if isinstance(item, tuple) and item[0] is SENTINEL_ERR:
                    raise item[1]
                yield item
        finally:
            # Mirror LocalChatSession.stream: only kill on abnormal consumer exit
            # to avoid closing the HTTP socket prematurely on a clean completion.
            if not sentinel_end_reached:
                self.kill_process()

    def kill_process(self) -> None:
        """Called by cancel_guard's watcher from a separate thread.
        Sets _kill_pending so a not-yet-stashed response will close on
        arrival; closes _current_response in place if already stashed."""
        self._kill_pending = True
        self._stream_kill_pending = True   # race flag for stream() producer
        r = self._current_response
        if r is not None:
            try:
                r.close()
            except Exception:
                pass
