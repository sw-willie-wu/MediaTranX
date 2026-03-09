"""
任務管理模組
管理背景任務的提交、執行和狀態追蹤
"""
import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional
from uuid import uuid4

from backend.api.schemas.common import TaskResponse, TaskStatus
from .progress_tracker import ProgressTracker, get_progress_tracker

logger = logging.getLogger(__name__)


class TaskManager:
    """
    任務管理器
    負責管理背景任務的生命週期
    """

    _instance: Optional["TaskManager"] = None

    def __new__(cls, *args, **kwargs):
        """單例模式"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self, max_workers: int = 4):
        if self._initialized:
            return

        self._tasks: Dict[str, TaskResponse] = {}
        self._futures: Dict[str, asyncio.Future] = {}
        self._progress_tracker = get_progress_tracker()
        self._executor = ThreadPoolExecutor(max_workers=max_workers)
        self._handlers: Dict[str, Callable] = {}
        self._initialized = True

        logger.info(f"TaskManager initialized with {max_workers} workers")

    @property
    def progress_tracker(self) -> ProgressTracker:
        return self._progress_tracker

    def register_task(self, task_id: str, task_type: str) -> None:
        """
        手動登記外部管理的任務（適用於 asyncio-based 長任務）
        任務由外部程式碼負責執行與 progress_tracker.emit，
        此方法只確保 task_id 存在於 _tasks 供 SSE 端點查詢。
        """
        task = TaskResponse(
            task_id=task_id,
            task_type=task_type,
            status=TaskStatus.PROCESSING,
            progress=0.0,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc)
        )
        self._tasks[task_id] = task
        logger.info(f"Task registered (external): {task_id} ({task_type})")

    def register_handler(self, task_type: str, handler: Callable) -> None:
        """
        註冊任務處理器

        Args:
            task_type: 任務類型 (e.g., "video.transcode", "image.upscale")
            handler: 處理函數，接收 (params, progress_callback) 參數
        """
        self._handlers[task_type] = handler
        logger.info(f"Registered handler for task type: {task_type}")

    async def submit(
        self,
        task_type: str,
        params: dict,
        priority: int = 0
    ) -> str:
        """
        提交新任務

        Args:
            task_type: 任務類型
            params: 任務參數
            priority: 優先級（目前未實作）

        Returns:
            task_id: 任務 ID
        """
        task_id = str(uuid4())

        task = TaskResponse(
            task_id=task_id,
            task_type=task_type,
            status=TaskStatus.PENDING,
            progress=0.0,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc)
        )
        self._tasks[task_id] = task

        # 在背景執行任務
        asyncio.create_task(self._execute_task(task_id, task_type, params))

        logger.info(f"Task submitted: {task_id} ({task_type})")
        return task_id

    async def _execute_task(
        self,
        task_id: str,
        task_type: str,
        params: dict
    ) -> None:
        """在背景執行任務"""
        task = self._tasks[task_id]

        try:
            # 檢查是否有註冊的處理器
            handler = self._handlers.get(task_type)
            if handler is None:
                raise ValueError(f"No handler registered for task type: {task_type}")

            # 更新狀態為處理中
            task.status = TaskStatus.PROCESSING
            task.updated_at = datetime.now(timezone.utc)

            # 建立進度回調
            progress_callback = self._progress_tracker.create_callback(task_id)

            # 在 executor 中執行（支援 CPU 密集型任務）
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                self._executor,
                lambda: handler(params, progress_callback)
            )

            # 任務完成
            task.status = TaskStatus.COMPLETED
            task.progress = 1.0
            task.result = result
            task.updated_at = datetime.now(timezone.utc)
            await self._progress_tracker.emit(
                task_id, 1.0, "Task completed",
                stage="completed",
                result=result if isinstance(result, dict) else None,
            )

            logger.info(f"Task completed: {task_id}")

        except Exception as e:
            # 任務失敗
            import traceback
            task.status = TaskStatus.FAILED
            task.error = str(e)
            task.updated_at = datetime.now(timezone.utc)
            await self._progress_tracker.emit(task_id, task.progress, f"Error: {e}")

            logger.error(f"Task failed: {task_id} - {e}\n{traceback.format_exc()}")

    def get_task(self, task_id: str) -> Optional[TaskResponse]:
        """取得任務狀態（進行中的任務會從 progress_tracker 同步最新進度）"""
        task = self._tasks.get(task_id)
        if task is None:
            return None
        if task.status in (TaskStatus.PENDING, TaskStatus.PROCESSING):
            latest = self._progress_tracker.get_progress(task_id)
            if latest is not None:
                task.progress = latest.progress
                if latest.message:
                    task.message = latest.message
        return task

    def get_all_tasks(self) -> List[TaskResponse]:
        """取得所有任務（進行中的任務會從 progress_tracker 同步最新進度）"""
        return [self.get_task(task_id) for task_id in list(self._tasks)]

    def get_active_tasks(self) -> List[TaskResponse]:
        """取得進行中的任務"""
        return [
            self.get_task(task_id) for task_id, task in list(self._tasks.items())
            if task.status in [TaskStatus.PENDING, TaskStatus.PROCESSING]
        ]

    async def cancel(self, task_id: str) -> bool:
        """
        取消任務

        Args:
            task_id: 任務 ID

        Returns:
            是否成功取消
        """
        task = self._tasks.get(task_id)
        if task is None:
            return False

        if task.status in [TaskStatus.PENDING, TaskStatus.PROCESSING]:
            task.status = TaskStatus.CANCELLED
            task.updated_at = datetime.now(timezone.utc)
            await self._progress_tracker.emit(task_id, task.progress, "Task cancelled")
            logger.info(f"Task cancelled: {task_id}")
            return True

        return False

    def remove(self, task_id: str) -> bool:
        """
        移除已完成的任務

        Args:
            task_id: 任務 ID

        Returns:
            是否成功移除
        """
        task = self._tasks.get(task_id)
        if task is None:
            return False

        if task.status in [TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED]:
            del self._tasks[task_id]
            self._progress_tracker.cleanup(task_id)
            logger.info(f"Task removed: {task_id}")
            return True

        return False

    def cleanup_completed(self, max_age_hours: int = 24) -> int:
        """
        清理過期的已完成任務

        Args:
            max_age_hours: 最大保留時間（小時）

        Returns:
            清理的任務數量
        """
        now = datetime.now(timezone.utc)
        to_remove = []

        for task_id, task in self._tasks.items():
            if task.status in [TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED]:
                age = (now - task.updated_at).total_seconds() / 3600
                if age > max_age_hours:
                    to_remove.append(task_id)

        for task_id in to_remove:
            self.remove(task_id)

        return len(to_remove)


# 全域任務管理器實例
_task_manager: Optional[TaskManager] = None


def get_task_manager() -> TaskManager:
    """取得全域任務管理器實例"""
    global _task_manager
    if _task_manager is None:
        _task_manager = TaskManager()
    return _task_manager
