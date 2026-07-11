"""max_concurrent_tasks setting: schema bounds + executor swap."""
import pytest
from pydantic import ValidationError

from app.schemas.compute_settings import ComputeSettings
from app.workers.progress_tracker import ProgressTracker
from app.workers.task_manager import TaskManager


def test_compute_settings_default_and_bounds():
    assert ComputeSettings().max_concurrent_tasks == 4
    assert ComputeSettings(max_concurrent_tasks=1).max_concurrent_tasks == 1
    with pytest.raises(ValidationError):
        ComputeSettings(max_concurrent_tasks=0)
    with pytest.raises(ValidationError):
        ComputeSettings(max_concurrent_tasks=9)


def test_set_max_workers_swaps_executor():
    tm = TaskManager(progress_tracker=ProgressTracker())
    old = tm._executor
    tm.set_max_workers(2)
    assert tm._executor is not old
    assert tm._executor._max_workers == 2
    tm.set_max_workers(99)  # clamp 到 8
    assert tm._executor._max_workers == 8


def test_queued_tasks_stay_pending_until_worker_picks_up():
    """status=PROCESSING 只在 worker 真正開跑時設定——排隊中的 task 維持 PENDING
    （否則 max_concurrent_tasks 對使用者不可見，e2e 抓到的回歸）。"""
    import asyncio
    import threading

    from app.schemas.task import TaskStatus

    tm = TaskManager(progress_tracker=ProgressTracker())
    tm.set_max_workers(1)

    release = threading.Event()

    def slow_handler(params, progress_callback):
        release.wait(timeout=10)
        return {}

    tm.register_handler("test.slow", slow_handler)

    async def run():
        t1 = await tm.submit("test.slow", {})
        t2 = await tm.submit("test.slow", {})
        # 讓 event loop 跑起 _execute_task、worker 撿走 t1
        for _ in range(50):
            await asyncio.sleep(0.02)
            if tm._tasks[t1].status == TaskStatus.PROCESSING:
                break
        assert tm._tasks[t1].status == TaskStatus.PROCESSING
        # t2 只能排隊：不得是 PROCESSING
        assert tm._tasks[t2].status == TaskStatus.PENDING
        release.set()
        for _ in range(100):
            await asyncio.sleep(0.05)
            if (tm._tasks[t1].status == TaskStatus.COMPLETED
                    and tm._tasks[t2].status == TaskStatus.COMPLETED):
                break
        assert tm._tasks[t1].status == TaskStatus.COMPLETED
        assert tm._tasks[t2].status == TaskStatus.COMPLETED

    asyncio.run(run())


def test_cancel_while_queued_never_runs_handler():
    """取消排隊中(PENDING)的 task:worker 釋出後不得開跑 handler、
    不得把 CANCELLED 蓋成 PROCESSING/COMPLETED(增量 review 抓到的回歸)。"""
    import asyncio
    import threading

    from app.schemas.task import TaskStatus

    tm = TaskManager(progress_tracker=ProgressTracker())
    tm.set_max_workers(1)

    release = threading.Event()
    ran = []

    def slow_handler(params, progress_callback):
        release.wait(timeout=10)
        return {}

    def tracked_handler(params, progress_callback):
        ran.append(True)
        return {}

    tm.register_handler("test.slow", slow_handler)
    tm.register_handler("test.tracked", tracked_handler)

    async def run():
        t1 = await tm.submit("test.slow", {})
        t2 = await tm.submit("test.tracked", {})
        for _ in range(50):
            await asyncio.sleep(0.02)
            if tm._tasks[t1].status == TaskStatus.PROCESSING:
                break
        assert tm._tasks[t2].status == TaskStatus.PENDING

        await tm.cancel(t2)
        assert tm._tasks[t2].status == TaskStatus.CANCELLED

        release.set()
        for _ in range(100):
            await asyncio.sleep(0.05)
            if tm._tasks[t1].status == TaskStatus.COMPLETED:
                break
        # 給 executor 一點時間消化(若回歸存在,t2 會在這裡被跑掉)
        await asyncio.sleep(0.3)

        assert ran == [], "cancelled queued task handler must never run"
        assert tm._tasks[t2].status == TaskStatus.CANCELLED
        # 備援 id 不得洩漏
        assert not tm.is_cancelled(t2)

    asyncio.run(run())
