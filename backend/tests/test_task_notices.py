from app.utils import task_notices as tn


def test_push_noop_without_active_sink():
    tn.push_task_notice("gpu_unsupported")  # must not raise


def test_push_appends_to_bound_sink():
    sink: list = []
    token = tn._current_task_notices.set(sink)
    try:
        tn.push_task_notice("vram_insufficient", model="whisper-medium")
        tn.push_task_notice("gpu_unsupported", model=None)  # None params dropped
    finally:
        tn._current_task_notices.reset(token)
    assert sink == [
        {"code": "vram_insufficient", "params": {"model": "whisper-medium"}},
        {"code": "gpu_unsupported", "params": {}},
    ]


def test_snapshot_returns_copy():
    sink = [{"code": "x", "params": {}}]
    snap = tn.snapshot_notices(sink)
    snap.append({"code": "y", "params": {}})
    assert len(sink) == 1
