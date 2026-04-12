"""
LLM chat service — direct LLM inference for chat and future agent use.
"""
import logging

logger = logging.getLogger(__name__)


class ChatService:
    """Direct LLM chat inference service."""

    def __init__(self):
        logger.info("ChatService initialized")

    def chat(
        self,
        prompt: str,
        model_family: str = "gemma4",
        model_size: str = "8b",
        max_tokens: int = 4096,
        temperature: float = 0.1,
    ) -> str:
        """Send a prompt directly to a local LLM and return the response."""
        from app.init.container import get_container

        runtime = get_container().llama_runtime()
        with runtime.acquire(model_family, model_size):
            return runtime.chat(
                messages=[{"role": "user", "content": prompt}],
                max_tokens=max_tokens,
                temperature=temperature,
            )
