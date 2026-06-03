from app.schemas.task import TaskData, TaskStatus
from app.api.routes.tasks.active import TaskResponse


def test_taskdata_notices_defaults_empty():
    t = TaskData(task_id="a", task_type="x")
    assert t.notices == []


def test_taskresponse_carries_notices_snapshot():
    t = TaskData(task_id="a", task_type="x", status=TaskStatus.PROCESSING)
    t.notices.append({"code": "vram_insufficient", "params": {"model": "whisper-medium"}})
    resp = TaskResponse.from_task_data(t)
    assert resp.notices == [{"code": "vram_insufficient", "params": {"model": "whisper-medium"}}]
    # mutating the task afterwards must not affect the already-built response
    t.notices.append({"code": "gpu_unsupported", "params": {}})
    assert len(resp.notices) == 1
