"""cancel_guard — pure cancel-watch + shared ContextVar single-poller coordination."""
import time
import pytest
from app.utils.inference import cancel_guard, fake_progress, _in_call_cancel_owner
from app.handler.exceptions import TaskCancelledError


class _Cancellable:
    def __init__(self, raise_on_kill=False):
        self.killed = 0
        self._raise = raise_on_kill
    def kill_process(self):
        self.killed += 1
        if self._raise:
            raise OSError("kill boom")


def test_passthrough_when_on_progress_none():
    c = _Cancellable()
    with cancel_guard(None, cancellable=c, progress=0.5, message="m"):
        pass
    assert c.killed == 0


def test_passthrough_when_cancellable_none():
    with cancel_guard(lambda p, m: None, cancellable=None, progress=0.5, message="m"):
        pass


def test_cancel_raises_kill_and_reraises():
    c = _Cancellable()
    def on_progress(p, m):
        raise TaskCancelledError("cancelled")
    with pytest.raises(TaskCancelledError):
        with cancel_guard(on_progress, cancellable=c, progress=0.4, message="x"):
            time.sleep(2.5)
    assert c.killed == 1


def test_kill_exception_swallowed_still_reraises():
    c = _Cancellable(raise_on_kill=True)
    def on_progress(p, m):
        raise TaskCancelledError("cancelled")
    with pytest.raises(TaskCancelledError):
        with cancel_guard(on_progress, cancellable=c, progress=0.4, message="x"):
            time.sleep(2.5)
    assert c.killed == 1


def test_passthrough_when_contextvar_already_set():
    """An enclosing owner (ContextVar set) → inner cancel_guard spawns NO watcher."""
    c = _Cancellable()
    seen = []
    tok = _in_call_cancel_owner.set(True)
    try:
        with cancel_guard(lambda p, m: seen.append(1), cancellable=c,
                          progress=0.5, message="m"):
            time.sleep(1.5)
    finally:
        _in_call_cancel_owner.reset(tok)
    assert seen == [], "inner guard must be pass-through when an owner exists"
    assert c.killed == 0


def test_fake_progress_enclosing_suppresses_inner_cancel_guard():
    """C1: fake_progress(cancellable=) is the owner; inner cancel_guard passes through."""
    c_outer = _Cancellable()
    c_inner = _Cancellable()
    inner_emitted = []

    def on_progress(p, m):
        raise TaskCancelledError("cancel")

    with pytest.raises(TaskCancelledError):
        with fake_progress(on_progress, 0.0, 1.0, "anim", duration=30,
                           cancellable=c_outer):
            with cancel_guard(lambda p, m: inner_emitted.append(1),
                              cancellable=c_inner, progress=0.5, message="m"):
                time.sleep(2.5)
    assert inner_emitted == []          # inner suppressed (single poller)
    assert c_outer.killed == 1          # fake_progress owner killed
    assert c_inner.killed == 0


def test_required_pct_msg_keyword_only():
    with pytest.raises(TypeError):
        cancel_guard(lambda p, m: None, cancellable=_Cancellable())


def test_contextvar_reset_after_block():
    c = _Cancellable()
    with cancel_guard(lambda p, m: None, cancellable=c, progress=0.1, message="a"):
        pass
    assert _in_call_cancel_owner.get() is False
