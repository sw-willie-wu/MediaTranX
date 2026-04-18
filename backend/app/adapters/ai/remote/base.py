"""
Remote Provider abstract base.
Shared interface for all external API providers (Ollama, OpenAI, Gemini).
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class RemoteModel:
    """Remote model information."""
    id: str              # Model ID (e.g. "llama3.2:3b")
    name: str            # Display name
    size: Optional[int] = None  # Model size (bytes)
    family: Optional[str] = None  # Model family
    parameter_size: Optional[str] = None  # Parameter count (e.g. "3B")
    quantization: Optional[str] = None  # Quantization level
    capabilities: list[str] = None  # ["text", "vision", "embedding"]

    def __post_init__(self):
        if self.capabilities is None:
            self.capabilities = ["text"]


class RemoteProvider(ABC):
    """
    Remote API Provider abstract interface.

    Subclasses must implement:
    - connect(): Verify connection
    - list_models(): List available models
    - chat(): Text conversation
    """

    def __init__(self, endpoint: str, api_key: Optional[str] = None):
        self.endpoint = endpoint.rstrip("/")
        self.api_key = api_key

    @abstractmethod
    def connect(self) -> bool:
        """
        Verify connection is working.

        Returns:
            True if connection succeeded.
        """
        ...

    @abstractmethod
    def list_models(self) -> list[RemoteModel]:
        """
        List all available models.

        Returns:
            List of RemoteModel.
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
        Text conversation.

        Args:
            model: Model ID.
            messages: [{"role": "user", "content": "..."}].
            max_tokens: Maximum response token count.
            temperature: Temperature.

        Returns:
            Model response text.
        """
        ...

    def is_available(self) -> bool:
        """Check if provider is available (defaults to calling connect)."""
        try:
            return self.connect()
        except Exception:
            return False
