"""
Setup 管理服務（精簡版）
SetupService singleton + 系統狀態查詢 + 各功能模組 delegation。
"""
import sys
import logging
from app.init.configs import SETTINGS
from app.workers.task_manager import TaskManager

from .model_download_service import handle_model_download
from .model_removal_service import remove_model

logger = logging.getLogger(__name__)


class SetupService:
    """環境設置服務"""

    def __init__(self, task_manager: TaskManager):
        # 向 TaskManager 註冊模型下載 handler
        task_manager.register_handler("setup.model_download", self._handle_model_download)
        logger.info("SetupService initialized, registered setup.model_download handler")

    async def get_system_status(self) -> dict:
        """取得詳細系統與環境狀態"""
        from pathlib import Path
        from app.engine.device import get_device_info, select_torch_index
        from app.init.container import get_container

        device = get_device_info()
        manager = get_container().model_manager()
        torch_idx = select_torch_index()
        return {
            "device": device,
            "llama_ready": manager.is_llama_ready(),
            "base_dir": SETTINGS.path.data,
            "python_version": sys.version.split()[0],
            "torch_index": torch_idx,
            "components": self._get_component_versions(SETTINGS),
        }

    @staticmethod
    def _get_component_versions(settings) -> dict:
        """取得二進位工具版本（.version JSON 或純文字）"""
        import json
        versions = {}
        for tool in ("ffmpeg", "fluidsynth", "llama"):
            vfile = settings.path.bin / tool / ".version"
            if vfile.exists():
                try:
                    versions[tool] = json.loads(vfile.read_text("utf-8").strip())
                except (json.JSONDecodeError, ValueError):
                    pass
        # PyTorch
        try:
            import torch
            versions["pytorch"] = {
                "tag": torch.__version__,
                "variant": "CUDA " + torch.version.cuda if torch.cuda.is_available() else "CPU",
            }
        except ImportError:
            pass
        return versions

    def _handle_model_download(self, params: dict, progress_callback) -> dict:
        """模型下載任務處理器（同步，由 ThreadPoolExecutor 執行）"""
        return handle_model_download(params, progress_callback)

    def remove_model(self, item_id: str) -> None:
        """刪除已下載的模型/工具檔案"""
        remove_model(item_id)
