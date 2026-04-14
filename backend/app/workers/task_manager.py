"""
Task management module.
Manages background task submission, execution, and status tracking.
"""
import asyncio
import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Literal, Optional
from uuid import uuid4

from app.handler.exceptions import TaskCancelledError
from app.schemas.task import TaskData, TaskStatus
from .progress_tracker import ProgressTracker

if TYPE_CHECKING:
    from app.services.files.file_service import FileService

logger = logging.getLogger(__name__)


def _collect_output_ids(result: dict) -> list[str]:
    """Collect all file_id strings from a handler result dict.

    Conventions:
      - any string key ending with '_file_id' with string value
      - 'output_files': list of dicts each containing 'file_id'
    Returns deduplicated list preserving insertion order.
    """
    seen: list[str] = []
    for key, value in result.items():
        if isinstance(value, str) and key.endswith("_file_id"):
            if value not in seen:
                seen.append(value)
        elif key == "output_files" and isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    fid = item.get("file_id")
                    if isinstance(fid, str) and fid not in seen:
                        seen.append(fid)
    return seen


class TaskManager:
    """
    Task manager.
    Manages the lifecycle of background tasks.
    """

    def __init__(
        self,
        progress_tracker: ProgressTracker,
        max_workers: int = 4,
        file_service: Optional["FileService"] = None,
    ):
        self._tasks: Dict[str, TaskData] = {}
        self._futures: Dict[str, asyncio.Future] = {}
        self._cancelled_ids: set[str] = set()
        self._lock = threading.Lock()
        self._progress_tracker = progress_tracker
        self._executor = ThreadPoolExecutor(max_workers=max_workers)
        self._handlers: Dict[str, Callable] = {}
        self._handler_policies: Dict[str, str] = {}
        self._file_service = file_service
        self._on_terminal_callbacks: List[Callable[[TaskData], None]] = []

        logger.info(f"TaskManager initialized with {max_workers} workers")

    @property
    def progress_tracker(self) -> ProgressTracker:
        return self._progress_tracker

    def on_terminal(self, callback: Callable[[TaskData], None]) -> None:
        """Register a callback for when a task enters a terminal state."""
        self._on_terminal_callbacks.append(callback)

    def _notify_terminal(self, task: TaskData) -> None:
        for cb in self._on_terminal_callbacks:
            try:
                cb(task)
            except Exception as e:
                logger.warning(f"on_terminal callback error: {e}")

    def register_task(self, task_id: str, task_type: str) -> None:
        """
        Manually register an externally managed task (for asyncio-based long tasks).
        """
        task = TaskData(
            task_id=task_id,
            task_type=task_type,
            status=TaskStatus.PROCESSING,
            progress=0.0,
        )
        with self._lock:
            self._tasks[task_id] = task
        logger.info(f"Task registered (external): {task_id} ({task_type})")

    def is_cancelled(self, task_id: str) -> bool:
        """Check whether a task has been requested to cancel."""
        with self._lock:
            return task_id in self._cancelled_ids

    def register_handler(
        self,
        task_type: str,
        handler: Callable,
        output_policy: Literal["history", "results"] = "history",
    ) -> None:
        """Register a task handler.

        Args:
            task_type: Unique task type key (e.g. "audio.transcribe")
            handler: Callable(params, progress_callback) -> dict
            output_policy:
              - "history": single same-type output (filmstrip / historyStack).
              - "results": enter Results drawer (cross-type, multi-output, or
                semantically new artefact).
              Runtime: "history" is downgraded to "results" when the handler
              actually produces multi-output or cross-type output.
        """
        self._handlers[task_type] = handler
        self._handler_policies[task_type] = output_policy
        logger.info(f"Registered handler for task type: {task_type} (policy={output_policy})")

    async def submit(
        self,
        task_type: str,
        params: dict,
        priority: int = 0
    ) -> str:
        """Submit a new task."""
        task_id = str(uuid4())

        task = TaskData(
            task_id=task_id,
            task_type=task_type,
            status=TaskStatus.PENDING,
            progress=0.0,
            label=params.get("label"),
        )
        with self._lock:
            self._tasks[task_id] = task

        asyncio.create_task(self._execute_task(task_id, task_type, params))

        logger.info(f"Task submitted: {task_id} ({task_type})")
        return task_id

    def _create_cancellable_callback(self, task_id: str) -> Callable[[float, str], None]:
        """Create a cancellable progress callback that checks the cancel flag on each progress report."""
        base_callback = self._progress_tracker.create_callback(task_id)
        lock = self._lock

        def callback(progress: float, message: str = "") -> None:
            with lock:
                cancelled = task_id in self._cancelled_ids
            if cancelled:
                raise TaskCancelledError(f"Task {task_id} cancelled")
            base_callback(progress, message)

        return callback

    async def _execute_task(
        self,
        task_id: str,
        task_type: str,
        params: dict
    ) -> None:
        """Execute a task in the background."""
        with self._lock:
            task = self._tasks[task_id]

        try:
            handler = self._handlers.get(task_type)
            if handler is None:
                raise ValueError(f"No handler registered for task type: {task_type}")

            task.status = TaskStatus.PROCESSING
            task.updated_at = datetime.now(timezone.utc)

            progress_callback = self._create_cancellable_callback(task_id)

            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                self._executor,
                lambda: handler(params, progress_callback)
            )

            task.status = TaskStatus.COMPLETED
            task.progress = 1.0
            task.result = result
            task.updated_at = datetime.now(timezone.utc)

            # ── Metadata tagging for Results drawer ─────────────────
            if self._file_service is not None and isinstance(result, dict):
                self._apply_output_metadata(task_type, params, result)

            await self._progress_tracker.emit(
                task_id, 1.0, "Task completed",
                stage="completed",
                result=result if isinstance(result, dict) else None,
            )

            logger.info(f"Task completed: {task_id}")
            self._notify_terminal(task)

        except TaskCancelledError:
            task.status = TaskStatus.CANCELLED
            task.updated_at = datetime.now(timezone.utc)
            with self._lock:
                self._cancelled_ids.discard(task_id)
            await self._progress_tracker.emit(task_id, task.progress, "Task cancelled")
            logger.info(f"Task cancelled (in handler): {task_id}")
            self._notify_terminal(task)

        except Exception as e:
            import traceback
            task.status = TaskStatus.FAILED
            from app.handler.exceptions import RemoteApiError
            if isinstance(e, RemoteApiError):
                task.error = f"[{e.code}] {e.detail}"
                task.error_code = e.code
            else:
                task.error = str(e)
                task.error_code = None
            task.updated_at = datetime.now(timezone.utc)
            await self._progress_tracker.emit(task_id, task.progress, f"Error: {e}")

            logger.error(f"Task failed: {task_id} - {e}\n{traceback.format_exc()}")
            self._notify_terminal(task)

    def _apply_output_metadata(self, task_type: str, params: dict, result: dict) -> None:
        """Tag registered outputs with tool_id / source_file_id / show_in_results.

        Writes sidecar for results-policy outputs so they survive restart.
        """
        from app.utils.media_kind import infer_kind  # local: cold-start friendly

        fs = self._file_service
        source_file_id = params.get("file_id")
        policy = self._handler_policies.get(task_type, "history")
        output_ids = _collect_output_ids(result)
        if not output_ids:
            return

        source_fd = fs.get_file(source_file_id) if source_file_id else None
        source_kind = infer_kind(source_fd.filename) if source_fd else None
        output_kinds = set()
        for fid in output_ids:
            fd = fs.get_file(fid)
            if fd:
                k = infer_kind(fd.filename)
                if k is not None:
                    output_kinds.add(k)

        effective = policy
        if policy == "history":
            cross_type = source_kind is not None and output_kinds and output_kinds != {source_kind}
            if len(output_ids) > 1 or cross_type:
                logger.warning(
                    f"Policy downgrade: {task_type} declared output_policy='history' "
                    f"but produced {len(output_ids)} output(s), kinds={output_kinds} "
                    f"(source kind={source_kind}). Change register_handler(..., "
                    f"output_policy='results') to silence this warning."
                )
                effective = "results"

        show_in_results = effective == "results"
        for fid in output_ids:
            fd = fs.get_file(fid)
            if fd is None:
                continue
            fd.metadata = {
                **(fd.metadata or {}),
                "tool_id": task_type,
                "source_file_id": source_file_id,
                "show_in_results": show_in_results,
            }
            if show_in_results:
                fs.write_sidecar(fid)

    def get_task(self, task_id: str) -> Optional[TaskData]:
        """Get task status (in-progress tasks sync latest progress from progress_tracker)."""
        with self._lock:
            task = self._tasks.get(task_id)
        if task is None:
            return None
        if task.status in (TaskStatus.PENDING, TaskStatus.PROCESSING):
            latest = self._progress_tracker.get_progress(task_id)
            if latest is not None:
                task.progress = latest.progress
                if latest.message:
                    task.message = latest.message
                if latest.stage == "completed":
                    task.status = TaskStatus.COMPLETED
                    task.result = latest.result
                    task.updated_at = datetime.now(timezone.utc)
                    self._notify_terminal(task)
                elif latest.stage == "error":
                    task.status = TaskStatus.FAILED
                    task.error = latest.message
                    task.updated_at = datetime.now(timezone.utc)
                    self._notify_terminal(task)
        return task

    def get_all_tasks(self) -> List[TaskData]:
        """Get all tasks (in-progress tasks sync latest progress from progress_tracker)."""
        with self._lock:
            task_ids = list(self._tasks)
        return [self.get_task(task_id) for task_id in task_ids]

    def get_active_tasks(self) -> List[TaskData]:
        """Get in-progress tasks."""
        with self._lock:
            active_ids = [
                task_id for task_id, task in self._tasks.items()
                if task.status in [TaskStatus.PENDING, TaskStatus.PROCESSING]
            ]
        return [self.get_task(task_id) for task_id in active_ids]

    async def cancel(self, task_id: str) -> bool:
        """Cancel a task."""
        with self._lock:
            task = self._tasks.get(task_id)
        if task is None:
            return False

        if task.status == TaskStatus.PENDING:
            task.status = TaskStatus.CANCELLED
            task.updated_at = datetime.now(timezone.utc)
            await self._progress_tracker.emit(task_id, task.progress, "Task cancelled")
            logger.info(f"Task cancelled (pending): {task_id}")
            self._notify_terminal(task)
            return True

        if task.status == TaskStatus.PROCESSING:
            with self._lock:
                self._cancelled_ids.add(task_id)
            logger.info(f"Task cancel requested: {task_id}")
            return True

        return False

    def remove(self, task_id: str) -> bool:
        """Remove a completed task."""
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                return False

            if task.status in [TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED]:
                del self._tasks[task_id]
                self._cancelled_ids.discard(task_id)
            else:
                return False

        self._progress_tracker.cleanup(task_id)
        logger.info(f"Task removed: {task_id}")
        return True

    def cleanup_completed(self, max_age_hours: int = 24) -> int:
        """Clean up expired completed tasks."""
        now = datetime.now(timezone.utc)
        with self._lock:
            to_remove = [
                task_id for task_id, task in self._tasks.items()
                if task.status in [TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED]
                and (now - task.updated_at).total_seconds() / 3600 > max_age_hours
            ]

        for task_id in to_remove:
            self.remove(task_id)

        return len(to_remove)

    def shutdown(self) -> None:
        """Graceful shutdown: cancel pending tasks, wait for executor."""
        logger.info("TaskManager shutting down...")
        with self._lock:
            pending_ids = [
                tid for tid, t in self._tasks.items()
                if t.status in (TaskStatus.PENDING, TaskStatus.PROCESSING)
            ]
            for tid in pending_ids:
                self._cancelled_ids.add(tid)

        self._executor.shutdown(wait=True, cancel_futures=True)
        logger.info("TaskManager shutdown complete")
