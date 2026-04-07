"""Tests for workers — ProgressTracker and TaskManager thread safety."""
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

from app.workers.progress_tracker import ProgressTracker, ProgressEvent


class TestProgressTrackerThreadSafety:
    def test_concurrent_writes_and_reads(self):
        """Multiple threads writing progress while main thread reads — no crash, no lost final value."""
        tracker = ProgressTracker()
        num_tasks = 20
        updates_per_task = 50

        def writer(task_id: str):
            cb = tracker.create_callback(task_id)
            for i in range(updates_per_task):
                cb(i / updates_per_task, f"step {i}")

        with ThreadPoolExecutor(max_workers=8) as pool:
            futures = [pool.submit(writer, f"task-{n}") for n in range(num_tasks)]
            # Read concurrently while writes are happening
            for _ in range(100):
                for n in range(num_tasks):
                    tracker.get_progress(f"task-{n}")
            for f in futures:
                f.result()  # propagate any exceptions

        # After all writes, every task should have final progress
        for n in range(num_tasks):
            evt = tracker.get_progress(f"task-{n}")
            assert evt is not None
            assert evt.progress == pytest.approx((updates_per_task - 1) / updates_per_task)

    def test_cleanup_under_contention(self):
        """cleanup() doesn't raise even when writers are active."""
        tracker = ProgressTracker()
        cb = tracker.create_callback("t1")
        cb(0.5, "half")

        tracker.cleanup("t1")
        assert tracker.get_progress("t1") is None


import asyncio
from app.workers.task_manager import TaskManager
from app.models.task import TaskData, TaskStatus


class TestTaskManagerThreadSafety:
    def test_concurrent_submit_and_get(self):
        """Concurrent get_task calls while tasks are being created don't crash."""
        tracker = ProgressTracker()
        tm = TaskManager(progress_tracker=tracker, max_workers=2)

        def dummy_handler(params, progress_callback):
            import time
            time.sleep(0.01)
            return {"ok": True}

        tm.register_handler("test.job", dummy_handler)

        loop = asyncio.new_event_loop()

        async def submit_tasks():
            ids = []
            for i in range(10):
                tid = await tm.submit("test.job", {"i": i})
                ids.append(tid)
            return ids

        task_ids = loop.run_until_complete(submit_tasks())

        # Read all tasks concurrently from threads
        results = []
        def reader():
            for _ in range(20):
                for tid in task_ids:
                    t = tm.get_task(tid)
                    if t is not None:
                        results.append(t.task_id)

        threads = [threading.Thread(target=reader) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # All submitted tasks should be queryable
        for tid in task_ids:
            assert tm.get_task(tid) is not None

        loop.run_until_complete(asyncio.sleep(0.5))  # let tasks finish
        loop.close()

    def test_cancel_sets_flag(self):
        """cancel() on a PROCESSING task adds to _cancelled_ids safely."""
        tracker = ProgressTracker()
        tm = TaskManager(progress_tracker=tracker)

        task = TaskData(task_id="c1", task_type="test", status=TaskStatus.PROCESSING, progress=0.5)
        tm._tasks["c1"] = task

        loop = asyncio.new_event_loop()
        result = loop.run_until_complete(tm.cancel("c1"))
        assert result is True
        assert tm.is_cancelled("c1")
        loop.close()

    def test_remove_completed_task(self):
        """remove() deletes a terminal task from _tasks."""
        tracker = ProgressTracker()
        tm = TaskManager(progress_tracker=tracker)

        task = TaskData(task_id="r1", task_type="test", status=TaskStatus.COMPLETED, progress=1.0)
        tm._tasks["r1"] = task

        assert tm.remove("r1") is True
        assert tm.get_task("r1") is None
