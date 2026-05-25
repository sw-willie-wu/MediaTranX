"""Unit tests for RemoteChatSession (remote-provider adapter)."""
from unittest.mock import MagicMock

from app.services._remote_chat import RemoteChatSession


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
