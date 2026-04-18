"""Unit tests for LlmWrapper (BaseWrapper subclass holding a LlamaServer)."""
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app.adapters.ai.wrapper.base import BaseWrapper
from app.adapters.ai.wrapper.llm import LlmWrapper


def test_is_base_runtime_subclass():
    assert issubclass(LlmWrapper, BaseWrapper)


def test_init_registers_slot():
    w = LlmWrapper(slot="llm")
    assert w.slot == "llm"
    assert not w.is_loaded()


def test_chat_before_load_raises():
    w = LlmWrapper(slot="llm")
    with pytest.raises(RuntimeError, match="not loaded"):
        w.chat(messages=[{"role": "user", "content": "hi"}])


def test_chat_delegates_to_server_and_strips_thinking(monkeypatch):
    """LlmWrapper.chat() calls LlamaServer.post_chat() and strips <think>...</think>."""
    w = LlmWrapper(slot="llm")
    mock_server = MagicMock()
    mock_server.post_chat.return_value = "<think>reasoning here</think>\nFinal answer."
    w._model = mock_server  # simulate post-load state

    out = w.chat(messages=[{"role": "user", "content": "q"}], max_tokens=100)

    mock_server.post_chat.assert_called_once()
    assert out == "Final answer."


def test_complete_delegates_to_server_and_strips_thinking():
    w = LlmWrapper(slot="llm")
    mock_server = MagicMock()
    mock_server.post_completion.return_value = "<think>x</think>hello"
    w._model = mock_server

    out = w.complete(prompt="p", max_tokens=50)

    mock_server.post_completion.assert_called_once()
    assert out == "hello"


def test_strip_thinking_without_tags_is_passthrough():
    assert LlmWrapper._strip_thinking("just text") == "just text"


def test_unload_stops_server():
    w = LlmWrapper(slot="llm")
    mock_server = MagicMock()
    w._model = mock_server
    w._current_config = {"model_id": "x"}

    w.unload()

    mock_server.stop.assert_called_once()
    assert not w.is_loaded()
