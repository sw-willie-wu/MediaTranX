"""
Setup management service.
SetupService singleton + system status query + feature module delegation.
"""
import sys
import logging
from typing import Callable
from app.adapters.ai.model_manager import ModelManager
from app.init.configs import SETTINGS
from app.workers.task_manager import TaskManager

from .model_download_service import handle_model_download
from .model_removal_service import remove_model

logger = logging.getLogger(__name__)


class SetupService:
    """Environment setup, system status, and model download/removal service."""

    def __init__(self, task_manager: TaskManager, model_manager: ModelManager):
        self._task_manager = task_manager
        self._model_manager = model_manager
        # Register model download handler with TaskManager
        task_manager.register_handler(
            "setup.model_download", self._handle_model_download,
            output_policy="history",
        )
        logger.info("SetupService initialized, registered setup.model_download handler")

    async def submit_model_download(self, item_id: str) -> str:
        """Submit a tool/model download task and return the task_id."""
        return await self._task_manager.submit("setup.model_download", {"id": item_id})

    async def get_system_status(self) -> dict:
        """Get detailed system and environment status."""
        from app.adapters.device import get_device_info, select_torch_index

        device = get_device_info()
        manager = self._model_manager
        torch_idx = select_torch_index()
        return {
            "device": device,
            "llama_ready": manager.is_llama_ready(),
            "base_dir": SETTINGS.path.root,
            "python_version": sys.version.split()[0],
            "torch_index": torch_idx,
            "components": self._get_component_versions(SETTINGS),
        }

    @staticmethod
    def _get_component_versions(settings) -> dict:
        """Get binary tool versions (.version JSON or plain text)."""
        import json
        versions = {}
        tool_dirs = {
            "ffmpeg": settings.path.ffmpeg,
            "llama": settings.path.llama,
            "soundfonts": settings.path.soundfonts,
        }
        for tool, tool_dir in tool_dirs.items():
            vfile = tool_dir / ".version"
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

    def _handle_model_download(self, params: dict, progress_callback: Callable[[float, str], None]) -> dict:
        """Model download task handler (synchronous, runs in ThreadPoolExecutor)."""
        return handle_model_download(params, progress_callback)

    def remove_model(self, item_id: str) -> None:
        """Delete downloaded model/tool files."""
        remove_model(item_id)
