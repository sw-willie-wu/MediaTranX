"""TaskHistoryDAO.get() unit tests (use the in-memory real_db fixture)."""
import pytest
from datetime import datetime, timezone

from app.db.dao.task_history_dao import TaskHistoryDAO


@pytest.fixture
def dao(real_db):
    return TaskHistoryDAO()


def _save_one(dao: TaskHistoryDAO, task_id: str = "task-1") -> None:
    dao.save(
        task_id=task_id,
        task_type="image.compress",
        status="completed",
        created_at=datetime(2026, 7, 4, 12, 0, 0, tzinfo=timezone.utc),
        completed_at=datetime(2026, 7, 4, 12, 0, 1, tzinfo=timezone.utc),
        error=None,
        error_code=None,
    )


def test_get_existing_returns_record(dao):
    _save_one(dao, "task-abc")
    result = dao.get("task-abc")
    assert result is not None
    assert result.task_id == "task-abc"
    assert result.task_type == "image.compress"


def test_get_missing_returns_none(dao):
    assert dao.get("nonexistent-task-id") is None
