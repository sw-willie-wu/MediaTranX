"""
Remote Provider 抽象基底
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
所有外部 API provider（Ollama、OpenAI、Gemini）的共用介面。
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class RemoteModel:
    """遠端模型資訊"""
    id: str              # 模型 ID（例如 "llama3.2:3b"）
    name: str            # 顯示名稱
    size: Optional[int] = None  # 模型大小（bytes）
    family: Optional[str] = None  # 模型家族
    parameter_size: Optional[str] = None  # 參數量（例如 "3B"）
    quantization: Optional[str] = None  # 量化等級
    capabilities: list[str] = None  # ["text", "vision", "embedding"]

    def __post_init__(self):
        if self.capabilities is None:
            self.capabilities = ["text"]


class RemoteProvider(ABC):
    """
    Remote API Provider 抽象介面

    子類需實作：
    - connect(): 驗證連線
    - list_models(): 列舉可用模型
    - chat(): 文字對話
    """

    def __init__(self, endpoint: str, api_key: Optional[str] = None):
        self.endpoint = endpoint.rstrip("/")
        self.api_key = api_key

    @abstractmethod
    def connect(self) -> bool:
        """
        驗證連線是否正常

        Returns:
            True 如果連線成功
        """
        ...

    @abstractmethod
    def list_models(self) -> list[RemoteModel]:
        """
        列舉所有可用模型

        Returns:
            RemoteModel 列表
        """
        ...

    @abstractmethod
    def chat(
        self,
        model: str,
        messages: list[dict],
        max_tokens: int = 2048,
        temperature: float = 0.1,
    ) -> str:
        """
        文字對話

        Args:
            model: 模型 ID
            messages: [{"role": "user", "content": "..."}]
            max_tokens: 最大回應 token 數
            temperature: 溫度

        Returns:
            模型回應文字
        """
        ...

    def is_available(self) -> bool:
        """檢查 provider 是否可用（預設呼叫 connect）"""
        try:
            return self.connect()
        except Exception:
            return False
