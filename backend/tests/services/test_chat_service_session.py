"""Unit tests for ChatService.session() + ChatSession."""
import pytest
from contextlib import contextmanager
from unittest.mock import MagicMock

from app.services.llm.chat_service import ChatService


@contextmanager
def _fake_acquire_ctx(*args, **kwargs):
    yield None  # ModelManager.acquire returns the runtime; we yield None since test passes the wrapper directly


def _fake_llama_runtime() -> MagicMock:
    """LlmWrapper-shaped mock with acquire as a contextmanager and chat/complete + _model._process."""
    rt = MagicMock()
    rt.acquire = MagicMock(side_effect=lambda *a, **kw: _fake_acquire_ctx())
    rt.chat = MagicMock(return_value="chat-text")
    rt.complete = MagicMock(return_value="completion-text")
    rt._model = MagicMock()
    rt._model._process = MagicMock()
    return rt


def test_session_acquires_and_releases():
    rt = _fake_llama_runtime()
    svc = ChatService(rt)
    with svc.session(model_family="gemma4", model_size="4b") as session:
        assert session is not None
    rt.acquire.assert_called_once()


def test_session_chat_forwards_to_runtime():
    rt = _fake_llama_runtime()
    svc = ChatService(rt)
    with svc.session(model_family="gemma4", model_size="4b") as session:
        out = session.chat(
            messages=[{"role": "user", "content": "hi"}],
            max_tokens=100, temperature=0.1,
        )
    assert out == "chat-text"
    rt.chat.assert_called_once()


def test_session_complete_forwards_to_runtime():
    rt = _fake_llama_runtime()
    svc = ChatService(rt)
    with svc.session(model_family="qwen3", model_size="4b") as session:
        out = session.complete(
            prompt="say hi", max_tokens=100, temperature=0.1,
        )
    assert out == "completion-text"
    rt.complete.assert_called_once()


def test_session_kill_process_routes_through_server_stop():
    rt = _fake_llama_runtime()
    svc = ChatService(rt)
    with svc.session(model_family="gemma4", model_size="4b") as session:
        # kill_process now clears rt._model after stop (so wrapper.is_loaded()
        # stops lying); capture the model ref upfront to keep the assertion.
        model_before_kill = rt._model
        session.kill_process()
    model_before_kill.stop.assert_called_once_with(timeout=2.0)
    assert rt._model is None  # cleared


def test_session_kill_process_safe_when_no_process():
    """kill_process is a best-effort hook — no-op if runtime not yet loaded or process gone."""
    rt = _fake_llama_runtime()
    rt._model = None  # not loaded
    svc = ChatService(rt)
    with svc.session(model_family="gemma4", model_size="4b") as session:
        session.kill_process()  # must not raise


def test_chat_with_images_builds_openai_compat_payload(tmp_path):
    """chat_with_images sends OpenAI-style messages with image_url data URIs."""
    rt = _fake_llama_runtime()
    svc = ChatService(rt)

    # Create a tiny test image
    from PIL import Image
    img_path = tmp_path / "tiny.png"
    Image.new("RGB", (8, 8), (128, 0, 0)).save(img_path)

    with svc.session(model_family="qwen3vl", model_size="2b") as session:
        session.chat_with_images(
            prompt="describe", images=[img_path], max_tokens=16, temperature=0.0,
        )

    # Inspect the messages payload sent to runtime.chat
    args, kwargs = rt.chat.call_args
    messages = kwargs["messages"]
    assert isinstance(messages, list)
    assert messages[0]["role"] == "user"
    content = messages[0]["content"]
    assert isinstance(content, list)
    assert any(part["type"] == "text" for part in content)
    image_parts = [p for p in content if p["type"] == "image_url"]
    assert len(image_parts) == 1
    url = image_parts[0]["image_url"]["url"]
    assert url.startswith("data:image/png;base64,")


def test_one_shot_chat_still_works():
    """Backward-compat: ChatService.chat(prompt, ...) (one-shot) opens its own session."""
    rt = _fake_llama_runtime()
    svc = ChatService(rt)
    out = svc.chat("hi", model_family="gemma4", model_size="4b",
                   max_tokens=100, temperature=0.1)
    assert out == "chat-text"
    rt.acquire.assert_called_once()
