"""Unit tests for pure LlamaServer binary adapter (subprocess + HTTP)."""
from unittest.mock import MagicMock, patch

import pytest

from app.adapters.binary.llama_server import LlamaServer
from app.adapters.ai.wrapper.base import BaseWrapper


def test_llama_server_is_not_a_base_runtime():
    """LlamaServer must be a plain class (binary adapter), not a BaseWrapper subclass."""
    assert not issubclass(LlamaServer, BaseWrapper)


def test_init_creates_empty_server():
    server = LlamaServer()
    assert server.port is None
    assert not server.is_running()


def test_stop_when_not_started_is_noop():
    server = LlamaServer()
    server.stop()  # must not raise
    assert server.port is None
