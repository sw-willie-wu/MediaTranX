"""fake_progress is UNCHANGED (keeps cancellable=) + sets ContextVar when owned."""
import inspect
import time
import pytest
from app.utils.inference import fake_progress, _in_call_cancel_owner
from app.handler.exceptions import TaskCancelledError


def test_fake_progress_still_has_cancellable_param():
    assert "cancellable" in inspect.signature(fake_progress).parameters


def test_fake_progress_kills_on_cancel():
    class C:
        killed = 0
        def kill_process(self):
            C.killed += 1
    def on_progress(p, m):
        raise TaskCancelledError("c")
    with pytest.raises(TaskCancelledError):
        with fake_progress(on_progress, 0.0, 1.0, "m", duration=30, cancellable=C()):
            time.sleep(2.0)
    assert C.killed == 1


def test_fake_progress_sets_contextvar_only_when_cancellable():
    class C:
        def kill_process(self):
            pass
    inside = {}
    with fake_progress(lambda p, m: None, 0.0, 1.0, "m", duration=30, cancellable=C()):
        inside["owned"] = _in_call_cancel_owner.get()
    assert inside["owned"] is True
    assert _in_call_cancel_owner.get() is False  # reset

    with fake_progress(lambda p, m: None, 0.0, 1.0, "m", duration=30):  # no cancellable
        inside["unowned"] = _in_call_cancel_owner.get()
    assert inside["unowned"] is False  # animation-only caller untouched


def test_animation_only_caller_still_cooperatively_reraises():
    def on_progress(p, m):
        raise TaskCancelledError("coop")
    with pytest.raises(TaskCancelledError):
        with fake_progress(on_progress, 0.0, 1.0, "m", duration=2):
            time.sleep(2.0)
