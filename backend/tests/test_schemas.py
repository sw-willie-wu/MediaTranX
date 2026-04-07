"""Tests for API schema serialization (Pydantic V2)."""
from datetime import datetime, timezone

from app.api.schemas.common import TaskResponse, ProgressUpdate, FileInfo


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


class TestProgressUpdateSerialization:
    def test_datetime_serializes_to_iso(self):
        now = datetime(2026, 1, 15, 10, 30, 0, tzinfo=timezone.utc)
        r = ProgressUpdate(task_id="t1", progress=0.5, timestamp=now)
        data = r.model_dump(mode="json")
        assert data["timestamp"] == "2026-01-15T10:30:00+00:00"

    def test_no_v1_config_class(self):
        assert not hasattr(ProgressUpdate, "Config")
