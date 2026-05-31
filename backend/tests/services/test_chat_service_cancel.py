"""ChatSession/ChatService self-guard wiring + single-poller (C1)."""
import time
from contextlib import contextmanager
from unittest.mock import MagicMock, patch
import pytest

from app.services.llm.chat_service import ChatService, ChatSession
from app.handler.exceptions import TaskCancelledError
from app.utils.inference import fake_progress


def _runtime():
    rt = MagicMock()
    rt.chat.return_value = "ok"
    rt.complete.return_value = "ok"
    rt._model = MagicMock()  # ChatSession.kill_process -> rt._model.stop
    return rt


@contextmanager
def _cm():
    yield None


def test_session_passthrough_when_no_on_progress():
    rt = _runtime()
    s = ChatSession(rt)
    assert s.chat(messages=[{"role": "user", "content": "x"}],
                  max_tokens=10, temperature=0.0) == "ok"
    rt.chat.assert_called_once()


def test_session_chat_guarded_when_on_progress():
    rt = _runtime()
    s = ChatSession(rt, on_progress=lambda p, m: None, cancel_pct=0.5, cancel_msg="m")
    with patch("app.services.llm.chat_service.cancel_guard") as cg:
        cg.return_value.__enter__ = MagicMock()
        cg.return_value.__exit__ = MagicMock(return_value=False)
        s.chat(messages=[{"role": "user", "content": "x"}],
               max_tokens=10, temperature=0.0)
    cg.assert_called_once()
    kw = cg.call_args.kwargs
    assert kw["cancellable"] is s and kw["progress"] == 0.5 and kw["message"] == "m"


def test_session_complete_and_images_guarded():
    rt = _runtime()
    s = ChatSession(rt, on_progress=lambda p, m: None, cancel_pct=0.3, cancel_msg="m")
    with patch("app.services.llm.chat_service.cancel_guard") as cg:
        cg.return_value.__enter__ = MagicMock()
        cg.return_value.__exit__ = MagicMock(return_value=False)
        s.complete(prompt="p", max_tokens=5, temperature=0.0)
    cg.assert_called_once()


def test_cancel_during_chat_kills_via_session_kill_process():
    rt = _runtime()
    def raising(p, m):
        raise TaskCancelledError("cancel")
    s = ChatSession(rt, on_progress=raising, cancel_pct=0.5, cancel_msg="m")
    def slow(**kw):
        time.sleep(2.5)
        return "late"
    rt.chat.side_effect = slow
    # kill_process now clears rt._model after stop (so wrapper.is_loaded()
    # stops lying on the next acquire), so capture the model ref upfront.
    model_before_kill = rt._model
    with pytest.raises(TaskCancelledError):
        s.chat(messages=[{"role": "user", "content": "x"}],
               max_tokens=10, temperature=0.0)
    # cancel_guard(cancellable=self) -> ChatSession.kill_process -> rt._model.stop
    model_before_kill.stop.assert_called()
    assert rt._model is None  # cleared so next acquire's is_loaded() tells truth


def test_single_poller_when_enclosing_fake_progress():
    """C1: fake_progress(cancellable=outer) wrapping a guarded session.chat
    → inner cancel_guard is pass-through (no second watcher)."""
    rt = _runtime()
    inner_emit = []

    def on_progress(p, m):  # fake_progress drives it; raises on tick
        raise TaskCancelledError("cancel")

    s = ChatSession(rt, on_progress=(lambda p, m: inner_emit.append(1)),
                    cancel_pct=0.5, cancel_msg="m")

    class Outer:
        killed = 0
        def kill_process(self):
            Outer.killed += 1

    def slow(**kw):
        time.sleep(2.5)
        return "x"
    rt.chat.side_effect = slow
    with pytest.raises(TaskCancelledError):
        with fake_progress(on_progress, 0.0, 1.0, "anim", duration=30,
                           cancellable=Outer()):
            s.chat(messages=[{"role": "user", "content": "x"}],
                   max_tokens=10, temperature=0.0)
    assert inner_emit == []        # inner ChatSession cancel_guard suppressed
    assert Outer.killed == 1       # the single (fake_progress) owner killed


def test_chatservice_session_threads_params():
    rt = _runtime()
    rt.acquire = MagicMock(side_effect=lambda *a, **k: _cm())
    svc = ChatService(rt)
    cb = lambda p, m: None
    with svc.session(model_family="g", model_size="4b",
                     on_progress=cb, cancel_pct=0.7, cancel_msg="mm") as ses:
        assert ses._on_progress is cb
        assert ses._cancel_pct == 0.7
        assert ses._cancel_msg == "mm"


def test_chatservice_oneshot_forwards_params():
    rt = _runtime()
    rt.acquire = MagicMock(side_effect=lambda *a, **k: _cm())
    svc = ChatService(rt)
    captured = {}
    real = svc.session

    def spy(**kw):
        captured.update(kw)
        return real(**kw)

    with patch.object(svc, "session", side_effect=spy):
        with patch.object(ChatSession, "chat", return_value="ok"):
            svc.chat(prompt="hi", model_family="g", model_size="4b",
                     on_progress=(lambda p, m: None), cancel_pct=0.2, cancel_msg="z")
    assert captured.get("cancel_pct") == 0.2
    assert captured.get("cancel_msg") == "z"
    assert "on_progress" in captured


def test_chat_session_alias_resolves_to_local_chat_session():
    """Backward-compat: existing imports of ChatSession get LocalChatSession."""
    from app.services.llm.chat_service import ChatSession, LocalChatSession
    assert ChatSession is LocalChatSession
