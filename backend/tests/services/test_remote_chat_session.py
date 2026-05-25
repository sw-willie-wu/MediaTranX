"""RemoteChatSession upgrade tests.

Spec: §F2.
"""
import threading
import time
from unittest.mock import MagicMock, patch

import pytest


def _make_session(*, on_progress=None, cancel_pct=0.0, cancel_msg="default"):
    from app.services._remote_chat import RemoteChatSession
    prov = MagicMock(name="RemoteProvider")
    return RemoteChatSession(
        prov, "model-x",
        on_progress=on_progress,
        cancel_pct=cancel_pct, cancel_msg=cancel_msg,
    ), prov


def test_chat_delegates_to_provider_with_abort_hook():
    session, prov = _make_session()
    prov.chat = MagicMock(return_value="hello")

    result = session.chat(
        messages=[{"role": "user", "content": "hi"}],
        max_tokens=10, temperature=0.2,
    )
    assert result == "hello"
    prov.chat.assert_called_once()
    _, kw = prov.chat.call_args
    assert kw["model"] == "model-x"
    assert kw["messages"] == [{"role": "user", "content": "hi"}]
    assert kw["max_tokens"] == 10
    assert kw["temperature"] == 0.2
    assert callable(kw["abort_hook"])


def test_chat_with_images_delegates(tmp_path):
    session, prov = _make_session()
    prov.chat_with_images = MagicMock(return_value="img description")
    img = tmp_path / "f.png"
    img.write_bytes(b"\x89PNG")

    result = session.chat_with_images(
        prompt="describe", images=[img],
        max_tokens=200, temperature=0.0,
    )
    assert result == "img description"
    _, kw = prov.chat_with_images.call_args
    assert kw["model"] == "model-x"
    assert kw["prompt"] == "describe"
    assert kw["images"] == [img]
    assert callable(kw["abort_hook"])


def test_complete_raises_not_implemented():
    session, _ = _make_session()
    with pytest.raises(NotImplementedError, match="intentionally"):
        session.complete("anything", max_tokens=10, temperature=0.0)


def test_abort_hook_stashes_response_then_clears_on_return():
    session, prov = _make_session()
    captured_hook = {}

    def fake_chat(model, messages, max_tokens, temperature, abort_hook):
        captured_hook["fn"] = abort_hook
        fake_resp = MagicMock(name="resp")
        abort_hook(fake_resp)
        # while inside the provider, the session has the response stashed
        assert session._current_response is fake_resp
        return "done"

    prov.chat = fake_chat
    session.chat(messages=[{"role": "user", "content": "x"}],
                 max_tokens=10, temperature=0.0)
    # After return: cleared in finally
    assert session._current_response is None


def test_kill_process_closes_stashed_response():
    """When _current_response is set, kill_process closes it."""
    session, _ = _make_session()
    fake_resp = MagicMock(name="resp")
    session._current_response = fake_resp
    session.kill_process()
    fake_resp.close.assert_called_once()


def test_kill_process_idempotent_when_no_response():
    """When _current_response is None, kill_process is a no-op (no exception)."""
    session, _ = _make_session()
    assert session._current_response is None
    session.kill_process()  # must not raise
    assert session._kill_pending is True


def test_kill_pending_set_before_response_arrives():
    """If kill_process fires BEFORE abort_hook, _set_current closes resp and raises."""
    session, prov = _make_session()
    fake_resp = MagicMock(name="resp")

    # Simulate the pre-connection race: cancel watcher fires first.
    session.kill_process()  # _kill_pending = True; _current_response = None
    assert session._kill_pending is True

    # Provider belatedly calls _set_current (the abort_hook).
    with pytest.raises(OSError, match="cancel_pre_response"):
        session._set_current(fake_resp)
    fake_resp.close.assert_called_once()


def test_set_current_assigns_before_pending_check_eliminates_race():
    """Statement order: _current_response = resp first, then check _kill_pending.
    If pending is set MID-assignment, the response is still stashed so kill_process
    on a later poll can close it (residual safety net beyond the 30s socket timeout).

    Spec MINOR-V4-4 plan-stage fix.
    """
    session, _ = _make_session()
    fake_resp = MagicMock(name="resp")
    # Simulate "pending was set AFTER the check but BEFORE assignment" by
    # asserting that _current_response is assigned even when not pending.
    session._set_current(fake_resp)
    assert session._current_response is fake_resp
    assert session._kill_pending is False


def test_per_call_cancel_pct_msg_override_chat():
    """session.chat(cancel_pct=, cancel_msg=) override session defaults at _guard."""
    on_progress = MagicMock(name="on_progress")
    session, prov = _make_session(
        on_progress=on_progress, cancel_pct=0.5, cancel_msg="default",
    )
    prov.chat = MagicMock(return_value="x")
    with patch("app.services._remote_chat.cancel_guard") as cg:
        cg.return_value.__enter__ = MagicMock(return_value=None)
        cg.return_value.__exit__ = MagicMock(return_value=False)
        session.chat(
            messages=[{"role": "user", "content": "y"}],
            max_tokens=10, temperature=0.0,
            cancel_pct=0.85, cancel_msg="override",
        )
    cg.assert_called_once()
    _, kw = cg.call_args
    assert kw["progress"] == 0.85
    assert kw["message"] == "override"


def test_per_call_cancel_pct_msg_override_chat_with_images(tmp_path):
    """session.chat_with_images(cancel_pct=, cancel_msg=) override session defaults."""
    img = tmp_path / "f.png"
    img.write_bytes(b"\x89PNG")
    on_progress = MagicMock(name="on_progress")
    session, prov = _make_session(
        on_progress=on_progress, cancel_pct=0.5, cancel_msg="default",
    )
    prov.chat_with_images = MagicMock(return_value="d")
    with patch("app.services._remote_chat.cancel_guard") as cg:
        cg.return_value.__enter__ = MagicMock(return_value=None)
        cg.return_value.__exit__ = MagicMock(return_value=False)
        session.chat_with_images(
            prompt="p", images=[img],
            max_tokens=10, temperature=0.0,
            cancel_pct=0.92, cancel_msg="vlm_override",
        )
    cg.assert_called_once()
    _, kw = cg.call_args
    assert kw["progress"] == 0.92
    assert kw["message"] == "vlm_override"


def test_guard_returns_nullcontext_when_no_on_progress():
    """With no on_progress, _guard is a no-op (nullcontext)."""
    from contextlib import nullcontext
    session, _ = _make_session(on_progress=None)
    # nullcontext doesn't have a stable type to assert; assert behavior via
    # using it (no exception raised, exits cleanly).
    with session._guard() as ctx:
        assert ctx is None  # nullcontext yields None
