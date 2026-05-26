"""ChatService dispatch + LocalChatSession per-call cancel override tests.

Spec: core/.claude/specs/2026-05-25-video-summary-remote-line.md §F3.
"""
from unittest.mock import MagicMock, patch

import pytest


def _build_local_session_with_override_defaults():
    """Construct a LocalChatSession via ChatService.session() with cancel defaults."""
    from app.services.llm.chat_service import ChatService

    rt = MagicMock(name="LlamaRuntime")
    # acquire() is a context manager that yields nothing in particular —
    # the session's chat() short-circuits before touching it via _guard.
    rt.acquire.return_value.__enter__ = MagicMock(return_value=None)
    rt.acquire.return_value.__exit__ = MagicMock(return_value=False)
    rt.chat = MagicMock(return_value="ok")

    svc = ChatService(llama_runtime=rt)
    on_progress = MagicMock(name="on_progress")
    cm = svc.session(
        model_family="gemma4", model_size="4b",
        on_progress=on_progress,
        cancel_pct=0.5, cancel_msg="default_msg",
    )
    return svc, rt, on_progress, cm


def test_local_chat_session_per_call_cancel_override_chat():
    """LocalChatSession.chat(cancel_pct=, cancel_msg=) overrides session defaults."""
    _svc, _rt, on_progress, cm = _build_local_session_with_override_defaults()
    with patch("app.services.llm.chat_service.cancel_guard") as cg:
        cg.return_value.__enter__ = MagicMock(return_value=None)
        cg.return_value.__exit__ = MagicMock(return_value=False)
        with cm as session:
            session.chat(
                messages=[{"role": "user", "content": "hi"}],
                max_tokens=10, temperature=0.0,
                cancel_pct=0.85, cancel_msg="override_msg",
            )
    cg.assert_called_once()
    _, kw = cg.call_args
    assert kw["progress"] == 0.85
    assert kw["message"] == "override_msg"


def test_local_chat_session_falls_back_to_session_default_when_no_override():
    """Without per-call kwargs, _guard uses session __init__ defaults."""
    _svc, _rt, on_progress, cm = _build_local_session_with_override_defaults()
    with patch("app.services.llm.chat_service.cancel_guard") as cg:
        cg.return_value.__enter__ = MagicMock(return_value=None)
        cg.return_value.__exit__ = MagicMock(return_value=False)
        with cm as session:
            session.chat(
                messages=[{"role": "user", "content": "hi"}],
                max_tokens=10, temperature=0.0,
            )  # no per-call override
    cg.assert_called_once()
    _, kw = cg.call_args
    assert kw["progress"] == 0.5
    assert kw["message"] == "default_msg"


def test_local_chat_session_per_call_cancel_override_chat_with_images(tmp_path):
    """LocalChatSession.chat_with_images() also honours per-call cancel override."""
    img = tmp_path / "t.png"
    img.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 64)
    _svc, _rt, on_progress, cm = _build_local_session_with_override_defaults()
    with patch("app.services.llm.chat_service.cancel_guard") as cg:
        cg.return_value.__enter__ = MagicMock(return_value=None)
        cg.return_value.__exit__ = MagicMock(return_value=False)
        with cm as session:
            session.chat_with_images(
                prompt="caption", images=[img],
                max_tokens=10, temperature=0.0,
                cancel_pct=0.92, cancel_msg="vlm_override",
            )
    cg.assert_called_once()
    _, kw = cg.call_args
    assert kw["progress"] == 0.92
    assert kw["message"] == "vlm_override"


def test_session_yields_remote_chat_session_when_provider_supplied():
    """session(remote_provider=..., remote_model=...) yields a RemoteChatSession
    and does NOT call llama_runtime.acquire."""
    from app.services.llm.chat_service import ChatService
    from app.services.llm.remote_chat import RemoteChatSession

    rt = MagicMock(name="LlamaRuntime")
    prov = MagicMock(name="OllamaProvider")
    svc = ChatService(llama_runtime=rt)

    with svc.session(
        remote_provider=prov, remote_model="qwen3.5:9b",
        on_progress=MagicMock(),
    ) as session:
        assert isinstance(session, RemoteChatSession)

    rt.acquire.assert_not_called()


def test_session_yields_local_chat_session_when_no_provider():
    """session(remote_provider=None, model_family=..., model_size=...) yields
    LocalChatSession and DOES call llama_runtime.acquire."""
    from app.services.llm.chat_service import ChatService, LocalChatSession

    rt = MagicMock(name="LlamaRuntime")
    rt.acquire.return_value.__enter__ = MagicMock(return_value=None)
    rt.acquire.return_value.__exit__ = MagicMock(return_value=False)
    svc = ChatService(llama_runtime=rt)

    with svc.session(model_family="gemma4", model_size="4b") as session:
        assert isinstance(session, LocalChatSession)

    rt.acquire.assert_called_once()


def test_session_remote_requires_model():
    """remote_provider without remote_model raises ValueError."""
    from app.services.llm.chat_service import ChatService

    rt = MagicMock(name="LlamaRuntime")
    prov = MagicMock(name="OllamaProvider")
    svc = ChatService(llama_runtime=rt)

    with pytest.raises(ValueError, match="remote_model"):
        with svc.session(remote_provider=prov, remote_model=None):
            pass


def test_session_local_requires_family_and_size():
    """No remote_provider AND missing model_family/model_size raises ValueError."""
    from app.services.llm.chat_service import ChatService

    rt = MagicMock(name="LlamaRuntime")
    svc = ChatService(llama_runtime=rt)

    with pytest.raises(ValueError, match="model_family"):
        with svc.session(model_family=None, model_size=None):
            pass


def test_one_shot_chat_forwards_remote_provider():
    """ChatService.chat(remote_provider=..., remote_model=...) routes through
    session() to RemoteChatSession."""
    from app.services.llm.chat_service import ChatService

    rt = MagicMock(name="LlamaRuntime")
    prov = MagicMock(name="OllamaProvider")
    prov.chat = MagicMock(return_value="remote reply")
    svc = ChatService(llama_runtime=rt)

    result = svc.chat(
        prompt="hello",
        remote_provider=prov, remote_model="qwen3.5:9b",
        max_tokens=10, temperature=0.1,
    )
    assert result == "remote reply"
    rt.acquire.assert_not_called()
    prov.chat.assert_called_once()
