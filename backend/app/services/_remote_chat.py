"""RemoteChatSession adapter — exposes ChatSession-compatible shape over a RemoteProvider.

Services use this to feed remote LLM calls into pipeline functions that
expect a ChatSession. The adapter only implements `chat` (remote providers
don't support `complete` or `chat_with_images` uniformly today; if needed,
extend on demand).
"""
from __future__ import annotations

from typing import Optional


class RemoteChatSession:
    """ChatSession-shaped wrapper around a (provider, model) pair."""

    def __init__(self, prov, model: str):
        self._prov = prov
        self._model = model

    def chat(
        self,
        messages: list[dict],
        *,
        max_tokens: int,
        temperature: float,
        top_k: int = 40,           # ignored by most providers
        top_p: float = 0.9,        # ignored by most providers
        stop: Optional[list[str]] = None,  # ignored
    ) -> str:
        return self._prov.chat(
            model=self._model, messages=messages,
            max_tokens=max_tokens, temperature=temperature,
        )

    def kill_process(self) -> None:
        """No-op for remote providers (no local subprocess)."""
        pass
