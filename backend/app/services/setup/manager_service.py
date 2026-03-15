"""
Setup 管理服務（精簡版）
SetupService singleton + 系統狀態查詢 + 各功能模組 delegation。
"""
import sys
import logging
import asyncio
from typing import Optional

from app.engine.paths import get_base_data_dir
from app.engine.device import get_device_info, select_torch_index

from .ai_env_service import initialize_ai_env
from .model_download_service import handle_model_download
from .model_removal_service import remove_model

logger = logging.getLogger(__name__)


class SetupService:
    """環境設置單例"""
    _instance: Optional["SetupService"] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._setup_lock = asyncio.Lock()
        self._initialized = True

        # 向 TaskManager 註冊模型下載 handler
        from app.workers.task_manager import get_task_manager
        get_task_manager().register_handler("setup.model_download", self._handle_model_download)
        logger.info("SetupService initialized, registered setup.model_download handler")

    async def get_system_status(self) -> dict:
        """取得詳細系統與環境狀態"""
        from app.engine.ai.model_manager import get_model_manager

        device = get_device_info()
        manager = get_model_manager()

        torch_idx = select_torch_index()
        return {
            "device": device,
            "ai_env_ready": manager.is_ai_env_ready(),
            "llama_ready": manager.is_llama_ready(),
            "base_dir": str(get_base_data_dir()),
            "python_version": sys.version.split()[0],
            "torch_index": torch_idx,
        }

    async def initialize_ai_env(self, task_id: str):
        """透過 uv 安裝 AI 運行環境"""
        await initialize_ai_env(self._setup_lock, task_id)

    def _handle_model_download(self, params: dict, progress_callback) -> dict:
        """模型下載任務處理器（同步，由 ThreadPoolExecutor 執行）"""
        return handle_model_download(params, progress_callback)

    def remove_model(self, item_id: str) -> None:
        """刪除已下載的模型/工具檔案"""
        remove_model(item_id)


def get_setup_service() -> SetupService:
    return SetupService()
