"""Tests for TaskHistoryService — thin wrapper around TaskHistoryDAO."""
from __future__ import annotations
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from app.services.tasks.history_service import TaskHistoryService


@pytest.fixture
def fake_dao():
    """Patch TaskHistoryDAO at instantiation site so the service uses a mock."""
    with patch("app.services.tasks.history_service.TaskHistoryDAO") as mock_cls:
        instance = MagicMock()
        instance.delete.return_value = True
        instance.clear.return_value = 0
        instance.query.return_value = {"items": [], "total": 0, "page": 1, "page_size": 30}
        mock_cls.return_value = instance
        yield instance


def test_save_forwards_all_kwargs(fake_dao):
    svc = TaskHistoryService()
    t_created = datetime(2026, 5, 19, 10, tzinfo=timezone.utc)
    t_done = datetime(2026, 5, 19, 11, tzinfo=timezone.utc)
    svc.save(
        task_id="t1", task_type="image.upscale", status="completed",
        created_at=t_created, completed_at=t_done,
        label="x4", file_name="img.png",
        error=None, error_code=None,
        result={"output_file_id": "out1"},
    )
    fake_dao.save.assert_called_once()
    kwargs = fake_dao.save.call_args.kwargs
    assert kwargs["task_id"] == "t1"
    assert kwargs["status"] == "completed"
    assert kwargs["result"] == {"output_file_id": "out1"}


def test_save_frontend_task_uses_now_for_timestamps(fake_dao):
    svc = TaskHistoryService()
    before = datetime.now(timezone.utc)
    svc.save_frontend_task(
        task_id="midi-1", task_type="midi.export", status="completed",
        label="export", file_name="song.mid",
    )
    after = datetime.now(timezone.utc)
    kwargs = fake_dao.save.call_args.kwargs
    assert before <= kwargs["created_at"] <= after
    # save_frontend_task fixes created_at == completed_at to "now"
    assert kwargs["created_at"] == kwargs["completed_at"]


def test_query_forwards_pagination(fake_dao):
    svc = TaskHistoryService()
    svc.query(page=3, page_size=50, status="completed")
    fake_dao.query.assert_called_once_with(page=3, page_size=50, status="completed")


def test_query_returns_dao_payload(fake_dao):
    fake_dao.query.return_value = {"items": [{"task_id": "t1"}], "total": 1, "page": 1, "page_size": 30}
    result = TaskHistoryService().query()
    assert result["total"] == 1


def test_delete_calls_dao(fake_dao):
    TaskHistoryService().delete("t1")
    fake_dao.delete.assert_called_once_with("t1")


def test_delete_missing_raises_not_found(fake_dao):
    from app.handler.exceptions import NotFoundError
    fake_dao.delete.return_value = False
    with pytest.raises(NotFoundError, match="History item not found"):
        TaskHistoryService().delete("missing-id")


def test_clear_returns_count(fake_dao):
    fake_dao.clear.return_value = 42
    assert TaskHistoryService().clear() == 42
