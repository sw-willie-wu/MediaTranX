"""Tests for app lifespan — startup and shutdown hooks."""
import pytest
from unittest.mock import patch, MagicMock

from app.init.configs import SETTINGS


class TestLifespan:
    @pytest.mark.asyncio
    async def test_startup_initializes_db(self):
        """Startup should call init_db."""
        with patch("app.init.lifespan.init_db") as mock_init_db, \
             patch("app.init.lifespan.get_container") as mock_get:
            mock_container = MagicMock()
            mock_get.return_value = mock_container
            mock_container.task_history.return_value = MagicMock()
            mock_container.task_manager.return_value = MagicMock()

            from app.init.lifespan import build_lifespan
            from fastapi import FastAPI

            app = FastAPI()
            lifespan = build_lifespan()

            async with lifespan(app):
                mock_init_db.assert_called_once()

    @pytest.mark.asyncio
    async def test_shutdown_calls_task_manager_shutdown(self):
        """Shutdown should call task_manager.shutdown(). Temp cleanup is now manual
        (via Results drawer / Settings 'clear temp' button), not automatic on exit.
        """
        mock_tm = MagicMock()
        mock_fs = MagicMock()
        mock_container = MagicMock()
        mock_container.task_manager.return_value = mock_tm
        mock_container.task_history.return_value = MagicMock()
        mock_container.file_service.return_value = mock_fs

        with patch("app.init.lifespan.init_db"), \
             patch("app.init.lifespan.get_container", return_value=mock_container):
            from app.init.lifespan import build_lifespan
            from fastapi import FastAPI

            app = FastAPI()
            lifespan = build_lifespan()

            async with lifespan(app):
                pass  # startup

            mock_tm.shutdown.assert_called_once()
            # Sidecar-based restore should have been invoked on startup
            mock_fs.scan_output_dir.assert_called_once()
            # cleanup_all must NOT be auto-called on shutdown
            mock_fs.cleanup_all.assert_not_called()


class TestPersistTerminalHistory:
    """_persist_terminal_history — module-level so it is unit-testable."""

    def test_persists_with_resolved_file_name(self):
        from app.init.lifespan import _persist_terminal_history
        from app.schemas.task import TaskData, TaskStatus

        history = MagicMock()
        fs = MagicMock()
        fs.get_file_name.return_value = "movie.mp4"
        task = TaskData(task_id="t1", task_type="video.summary",
                        status=TaskStatus.COMPLETED, file_id="f1")

        _persist_terminal_history(history, fs, task)

        fs.get_file_name.assert_called_once_with("f1")
        history.save.assert_called_once()
        kwargs = history.save.call_args.kwargs
        assert kwargs["task_id"] == "t1"
        assert kwargs["file_name"] == "movie.mp4"

    def test_persists_none_file_name_when_no_file_id(self):
        from app.init.lifespan import _persist_terminal_history
        from app.schemas.task import TaskData, TaskStatus

        history = MagicMock()
        fs = MagicMock()
        fs.get_file_name.return_value = None
        task = TaskData(task_id="t2", task_type="llm.chat",
                        status=TaskStatus.COMPLETED, file_id=None)

        _persist_terminal_history(history, fs, task)

        kwargs = history.save.call_args.kwargs
        assert kwargs["file_name"] is None
