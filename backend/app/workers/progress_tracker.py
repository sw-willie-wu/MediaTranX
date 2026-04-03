"""
進度追蹤模組
"""
import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Dict, Optional

logger = logging.getLogger(__name__)


@dataclass
class ProgressEvent:
    """進度事件"""
    task_id: str
    progress: float
    stage: str
    message: str
    result: Optional[dict] = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class ProgressTracker:
    """進度追蹤器，供 polling 查詢最新進度"""

    def __init__(self):
        self._latest_progress: Dict[str, ProgressEvent] = {}
        self._lock = threading.Lock()

    async def emit(
        self,
        task_id: str,
        progress: float,
        message: str = "",
        stage: str = "processing",
        result: Optional[dict] = None,
    ) -> None:
        with self._lock:
            self._latest_progress[task_id] = ProgressEvent(
                task_id=task_id,
                progress=min(max(progress, 0.0), 1.0),
                stage=stage,
                message=message,
                result=result,
            )
        logger.debug(f"Task {task_id}: {progress:.1%} - {message}")

    def create_callback(self, task_id: str) -> Callable[[float, str], None]:
        """
        建立同步的進度回調函數（用於 ThreadPoolExecutor 中的 handler）
        """
        lock = self._lock
        progress_dict = self._latest_progress

        def callback(progress: float, message: str = "") -> None:
            with lock:
                progress_dict[task_id] = ProgressEvent(
                    task_id=task_id,
                    progress=min(max(progress, 0.0), 1.0),
                    stage="processing",
                    message=message,
                )
            logger.debug(f"Task {task_id}: {progress:.1%} - {message}")

        return callback

    def get_progress(self, task_id: str) -> Optional[ProgressEvent]:
        """取得任務的最新進度"""
        with self._lock:
            return self._latest_progress.get(task_id)

    def cleanup(self, task_id: str) -> None:
        """清理任務的進度記錄"""
        with self._lock:
            self._latest_progress.pop(task_id, None)
