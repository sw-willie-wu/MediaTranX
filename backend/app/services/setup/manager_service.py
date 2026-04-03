"""
Setup 管理服務（精簡版）
SetupService singleton + 系統狀態查詢 + 各功能模組 delegation。
"""
import sys
import logging
import asyncio
from app.init.configs import get_settings
from app.workers.task_manager import TaskManager

from .ai_env_service import initialize_ai_env
from .model_download_service import handle_model_download
from .model_removal_service import remove_model

logger = logging.getLogger(__name__)


def _detect_installed_torch() -> str | None:
    """偵測 .venv 中實際安裝的 torch 版本，回傳如 '2.10.0+cu124' 或 None。"""
    try:
        import torch
        return torch.__version__
    except ImportError:
        return None


class SetupService:
    """環境設置服務"""

    def __init__(self, task_manager: TaskManager):
        self._setup_lock = asyncio.Lock()

        # 向 TaskManager 註冊模型下載 handler
        task_manager.register_handler("setup.model_download", self._handle_model_download)
        logger.info("SetupService initialized, registered setup.model_download handler")

    async def get_system_status(self) -> dict:
        """取得詳細系統與環境狀態"""
        from app.engine.device import get_device_info, select_torch_index
        from app.init.container import get_container

        device = get_device_info()
        manager = get_container().model_manager()
        torch_idx = select_torch_index()
        return {
            "device": device,
            "ai_env_ready": manager.is_ai_env_ready(),
            "llama_ready": manager.is_llama_ready(),
            "base_dir": get_settings().path.data,
            "python_version": sys.version.split()[0],
            "torch_index": torch_idx,
            "torch_installed": _detect_installed_torch(),
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
