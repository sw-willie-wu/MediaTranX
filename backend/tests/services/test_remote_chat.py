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


def test_kill_process_is_noop_for_remote():
    """Remote sessions can't kill anything — just no-op."""
    prov = MagicMock()
    session = RemoteChatSession(prov=prov, model="gpt-4o")
    session.kill_process()  # must not raise
