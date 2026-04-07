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
        """Shutdown should call task_manager.shutdown() and file_service.cleanup_all()."""
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

            # shutdown should have happened
            mock_tm.shutdown.assert_called_once()
            mock_fs.cleanup_all.assert_called_once()
