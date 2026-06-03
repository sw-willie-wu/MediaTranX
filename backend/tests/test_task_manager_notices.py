import asyncio
from app.workers.task_manager import TaskManager
from app.workers.progress_tracker import ProgressTracker
from app.utils.task_notices import push_task_notice


def _make_tm():
    return TaskManager(progress_tracker=ProgressTracker())


def test_handler_can_push_notice_into_its_task():
    tm = _make_tm()

    def handler(params, progress):
        push_task_notice("vram_insufficient", model="whisper-medium")
        return {"ok": True}

    tm.register_handler("notice.demo", handler)

    async def run():
        task_id = await tm.submit("notice.demo", {})
        for _ in range(200):
            t = tm.require_task(task_id)
            if t.status.value in ("completed", "failed"):
                return t
            await asyncio.sleep(0.02)
        raise AssertionError("task did not finish")

    t = asyncio.run(run())
    assert t.notices == [{"code": "vram_insufficient", "params": {"model": "whisper-medium"}}]


def test_failed_gpu_task_gets_classified_error_code():
    tm = _make_tm()

    def handler(params, progress):
        raise RuntimeError("CUDA error: no kernel image is available for execution")

    tm.register_handler("boom.gpu", handler)

    async def run():
        task_id = await tm.submit("boom.gpu", {})
        for _ in range(200):
            t = tm.require_task(task_id)
            if t.status.value == "failed":
                return t
            await asyncio.sleep(0.02)
        raise AssertionError("task did not fail")

    t = asyncio.run(run())
    assert t.error_code == "gpu_unsupported"
