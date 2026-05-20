"""Tests for API schema serialization (Pydantic V2).

`ProgressUpdate` was removed during the audit refactor — progress is now
emitted from `app.workers.progress_tracker.ProgressEvent` (an internal
dataclass, not a Pydantic model), so there's no public Pydantic surface to
test for it. `TaskResponse` lives in `routes/tasks/active.py` and `FileInfo`
in `routes/files/browse.py` (inline DTO per audit §1.2.1).
"""
from datetime import datetime, timezone
from unittest.mock import MagicMock

from app.api.routes.tasks.active import TaskResponse
from app.api.routes.files.browse import FileInfo  # noqa: F401 — imported to ensure module loads
from app.schemas.task import TaskData


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


class TestTaskResponseFromTaskData:
    def test_carries_file_id_without_resolver(self):
        t = TaskData(task_id="t1", task_type="video.summary", file_id="f1")
        r = TaskResponse.from_task_data(t)
        assert r.file_id == "f1"
        assert r.file_name is None

    def test_resolves_file_name_with_service(self):
        t = TaskData(task_id="t1", task_type="video.summary", file_id="f1")
        fs = MagicMock()
        fs.get_file_name.return_value = "clip.mp4"
        r = TaskResponse.from_task_data(t, fs)
        assert r.file_id == "f1"
        assert r.file_name == "clip.mp4"
        fs.get_file_name.assert_called_once_with("f1")

    def test_none_file_id_yields_none_file_name(self):
        t = TaskData(task_id="t1", task_type="llm.chat", file_id=None)
        fs = MagicMock()
        fs.get_file_name.return_value = None
        r = TaskResponse.from_task_data(t, fs)
        assert r.file_id is None
        assert r.file_name is None
