"""
Progress tracking module.
"""
import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Dict, Optional

logger = logging.getLogger(__name__)


@dataclass
class ProgressEvent:
    """Progress event."""
    task_id: str
    progress: float
    stage: str
    message: str
    result: Optional[dict] = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class ProgressTracker:
    """Progress tracker for polling the latest progress."""

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
        Create a synchronous progress callback (for handlers in ThreadPoolExecutor).
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
        """Get the latest progress for a task."""
        with self._lock:
            return self._latest_progress.get(task_id)

    def cleanup(self, task_id: str) -> None:
        """Clean up progress records for a task."""
        with self._lock:
            self._latest_progress.pop(task_id, None)
