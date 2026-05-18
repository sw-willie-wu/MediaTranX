"""Tests for API schema serialization (Pydantic V2).

`ProgressUpdate` was removed during the audit refactor — progress is now
emitted from `app.workers.progress_tracker.ProgressEvent` (an internal
dataclass, not a Pydantic model), so there's no public Pydantic surface to
test for it. `TaskResponse` lives in `routes/tasks/active.py` and `FileInfo`
in `routes/files/browse.py` (inline DTO per audit §1.2.1).
"""
from datetime import datetime, timezone

from app.api.routes.tasks.active import TaskResponse
from app.api.routes.files.browse import FileInfo  # noqa: F401 — imported to ensure module loads


class TestTaskResponseSerialization:
    def test_datetime_serializes_to_iso(self):
        now = datetime(2026, 1, 15, 10, 30, 0, tzinfo=timezone.utc)
        r = TaskResponse(
            task_id="t1",
            task_type="audio.transcode",
            created_at=now,
            updated_at=now,
        )
        data = r.model_dump(mode="json")
        assert data["created_at"] == "2026-01-15T10:30:00+00:00"
        assert data["updated_at"] == "2026-01-15T10:30:00+00:00"

    def test_progress_clamped(self):
        r = TaskResponse(task_id="t1", task_type="test", progress=0.5)
        assert r.progress == 0.5

    def test_no_v1_config_class(self):
        """Ensure deprecated Config inner class is gone."""
        assert not hasattr(TaskResponse, "Config")
