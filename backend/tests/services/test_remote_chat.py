"""Unit tests for RemoteChatSession (remote-provider adapter)."""
import threading
from unittest.mock import MagicMock

import pytest

from app.services.llm.remote_chat import RemoteChatSession


def test_chat_forwards_to_provider():
    prov = MagicMock()
    prov.chat = MagicMock(return_value="remote-text")
    session = RemoteChatSession(prov=prov, model="gpt-4o")
    out = session.chat(
        messages=[{"role": "user", "content": "hi"}], max_tokens=100, temperature=0.1,
    )
    assert out == "remote-text"
    args, kwargs = prov.chat.call_args
    assert kwargs["model"] == "gpt-4o"
    assert kwargs["max_tokens"] == 100


def test_kill_process_closes_stashed_response_when_present():
    """kill_process closes _current_response when set; idempotent otherwise.
    Sets _kill_pending=True so a subsequent _set_current call also closes.

    Replaced the old `is_noop_for_remote` assertion when RemoteChatSession
    was a thin wrapper; spec §F2 v3 upgrade.
    """
    prov = MagicMock(name="prov")
    session = RemoteChatSession(prov, "m")
    fake_resp = MagicMock()
    session._current_response = fake_resp
    session.kill_process()
    fake_resp.close.assert_called_once()
    assert session._kill_pending is True

    # idempotent — second kill is safe
    session.kill_process()
    assert session._kill_pending is True


def test_kill_process_no_response_only_sets_pending():
    """kill_process with no response stashed only sets _kill_pending."""
    prov = MagicMock(name="prov")
    session = RemoteChatSession(prov, "m")
    assert session._current_response is None
    session.kill_process()  # must not raise
    assert session._kill_pending is True


def test_session_cancel_surfaces_taskcancelled():
    """on_progress raising TaskCancelledError → kill_process closes resp →
    provider OSError → cancel_guard re-raises TaskCancelledError."""
    from app.handler.exceptions import TaskCancelledError

    killed = threading.Event()

    def fake_chat(*, model, messages, max_tokens, temperature, abort_hook, task=None):
        resp = MagicMock()
        resp.close.side_effect = lambda: killed.set()
        abort_hook(resp)                       # stash the closable response
        assert killed.wait(3.0), "kill_process was never called"
        raise OSError("socket closed by kill_process")

    prov = MagicMock()
    prov.chat = fake_chat

    def on_progress(p, m):
        raise TaskCancelledError("user cancelled")

    session = RemoteChatSession(prov, "m", on_progress=on_progress, cancel_pct=0.5)
    with pytest.raises(TaskCancelledError):
        session.chat(messages=[{"role": "user", "content": "x"}], max_tokens=10, temperature=0.0)
