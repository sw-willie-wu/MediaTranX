"""
進度追蹤模組
支援 SSE (Server-Sent Events) 即時進度推送
"""
import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import AsyncGenerator, Callable, Dict, Optional, Set

logger = logging.getLogger(__name__)


@dataclass
class ProgressEvent:
    """進度事件"""
    task_id: str
    progress: float
    stage: str
    message: str
    result: Optional[dict] = None
    timestamp: datetime = field(default_factory=datetime.utcnow)

    def to_json(self) -> str:
        data = {
            "task_id": self.task_id,
            "progress": self.progress,
            "stage": self.stage,
            "message": self.message,
            "timestamp": self.timestamp.isoformat()
        }
        if self.result is not None:
            data["result"] = self.result
        return json.dumps(data)


class ProgressTracker:
    """
    進度追蹤器
    管理任務進度並透過 SSE 推送給訂閱者
    """

    def __init__(self):
        self._subscribers: Dict[str, Set[asyncio.Queue]] = {}
        self._latest_progress: Dict[str, ProgressEvent] = {}
        self._lock = asyncio.Lock()

    async def emit(
        self,
        task_id: str,
        progress: float,
        message: str = "",
        stage: str = "processing",
        result: Optional[dict] = None,
    ) -> None:
        """
        發送進度更新給所有訂閱者

        Args:
            task_id: 任務 ID
            progress: 進度 (0.0 - 1.0)
            message: 進度訊息
            stage: 處理階段
        """
        event = ProgressEvent(
            task_id=task_id,
            progress=min(max(progress, 0.0), 1.0),
            stage=stage,
            message=message,
            result=result,
        )

        self._latest_progress[task_id] = event

        async with self._lock:
            if task_id in self._subscribers:
                dead_queues = []
                for queue in self._subscribers[task_id]:
                    try:
                        queue.put_nowait(event)
                    except asyncio.QueueFull:
                        dead_queues.append(queue)

                # 移除已滿的佇列
                for queue in dead_queues:
                    self._subscribers[task_id].discard(queue)

        logger.debug(f"Task {task_id}: {progress:.1%} - {message}")

    def create_callback(self, task_id: str) -> Callable[[float, str], None]:
        """
        建立同步的進度回調函數（用於非異步環境，如 ThreadPoolExecutor）

        會將進度事件安全地調度回主事件循環，確保 SSE 訂閱者能正確收到更新。

        Args:
            task_id: 任務 ID

        Returns:
            回調函數
        """
        # 捕獲主事件循環的參考（此方法在主循環上被呼叫）
        try:
            main_loop = asyncio.get_running_loop()
        except RuntimeError:
            main_loop = None

        tracker = self

        def callback(progress: float, message: str = "") -> None:
            # 直接更新最新進度（供心跳和查詢用）
            tracker._latest_progress[task_id] = ProgressEvent(
                task_id=task_id,
                progress=min(max(progress, 0.0), 1.0),
                stage="processing",
                message=message
            )

            # 透過主事件循環發送給 SSE 訂閱者
            if main_loop is not None and main_loop.is_running():
                asyncio.run_coroutine_threadsafe(
                    tracker.emit(task_id, progress, message),
                    main_loop
                )
            else:
                logger.debug(f"Task {task_id}: {progress:.1%} - {message}")

        return callback

    async def subscribe(self, task_id: str) -> AsyncGenerator[ProgressEvent, None]:
        """
        訂閱任務進度更新 (SSE 使用)

        Args:
            task_id: 任務 ID

        Yields:
            ProgressEvent: 進度事件
        """
        queue: asyncio.Queue = asyncio.Queue(maxsize=100)

        async with self._lock:
            if task_id not in self._subscribers:
                self._subscribers[task_id] = set()
            self._subscribers[task_id].add(queue)

        # 先發送最新進度（如果有的話）
        if task_id in self._latest_progress:
            yield self._latest_progress[task_id]

        try:
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=30.0)
                    yield event

                    # 只在 stage="completed" 或 stage="error" 時才結束訂閱
                    # 不能只看 progress >= 1.0：handler 的 progress_callback(1.0)
                    # 與 task_manager 最終帶 result 的 emit 都是 progress=1.0，
                    # 但只有後者的 stage 是 "completed"
                    if event.stage in ("completed", "error"):
                        break
                except asyncio.TimeoutError:
                    # 發送心跳以保持連線，保留最後一次的進度訊息
                    latest = self._latest_progress.get(task_id, ProgressEvent(
                        task_id=task_id, progress=0, stage="waiting", message=""
                    ))
                    yield ProgressEvent(
                        task_id=task_id,
                        progress=latest.progress,
                        stage="heartbeat",
                        message=latest.message or "處理中..."
                    )
        finally:
            async with self._lock:
                if task_id in self._subscribers:
                    self._subscribers[task_id].discard(queue)
                    if not self._subscribers[task_id]:
                        del self._subscribers[task_id]

    def get_progress(self, task_id: str) -> Optional[ProgressEvent]:
        """取得任務的最新進度"""
        return self._latest_progress.get(task_id)

    def cleanup(self, task_id: str) -> None:
        """清理任務的進度記錄"""
        self._latest_progress.pop(task_id, None)
        self._subscribers.pop(task_id, None)
