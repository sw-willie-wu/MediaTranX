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

from contextlib import nullcontext
from typing import Callable, Optional, Protocol

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
        self._kill_pending: bool = False    # set by kill_process before resp ready

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
    ) -> str:
        with self._guard(cancel_pct, cancel_msg):
            try:
                return self._prov.chat(
                    model=self._model, messages=messages,
                    max_tokens=max_tokens, temperature=temperature,
                    abort_hook=self._set_current,
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
    ) -> str:
        with self._guard(cancel_pct, cancel_msg):
            try:
                return self._prov.chat_with_images(
                    model=self._model, prompt=prompt, images=images,
                    max_tokens=max_tokens, temperature=temperature,
                    abort_hook=self._set_current,
                )
            finally:
                self._current_response = None

    def kill_process(self) -> None:
        """Called by cancel_guard's watcher from a separate thread.
        Sets _kill_pending so a not-yet-stashed response will close on
        arrival; closes _current_response in place if already stashed."""
        self._kill_pending = True
        r = self._current_response
        if r is not None:
            try:
                r.close()
            except Exception:
                pass
