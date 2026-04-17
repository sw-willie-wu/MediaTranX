"""
Remote API connection management service.
Manages external AI API connection settings (Ollama, OpenAI, Gemini).
"""
import logging
from typing import Optional

from app.db.dao.api_connection_dao import ApiConnectionDAO

logger = logging.getLogger(__name__)


class RemoteService:
    """Remote AI API connection management (Ollama, OpenAI, Gemini)."""

    def __init__(self):
        self._dao = ApiConnectionDAO()
        logger.info("RemoteService initialized")

    def get_connections(self, provider: Optional[str] = None) -> list[dict]:
        """Get connection list."""
        if provider:
            conns = self._dao.get_by_provider(provider)
        else:
            conns = self._dao.get_all()
        return [c.model_dump() for c in conns]

    def add_connection(
        self,
        provider: str,
        name: str,
        endpoint: str,
        api_key: Optional[str] = None,
    ) -> dict:
        """Add a new connection."""
        conn = self._dao.create(
            provider=provider,
            name=name,
            endpoint=endpoint,
            api_key=api_key,
        )
        return conn.model_dump()

    def update_connection(self, conn_id: int, **kwargs) -> Optional[dict]:
        """Update a connection."""
        conn = self._dao.update(conn_id, **kwargs)
        return conn.model_dump() if conn else None

    def delete_connection(self, conn_id: int) -> bool:
        """Delete a connection."""
        return self._dao.delete(conn_id)

    def test_connection(self, provider: str, endpoint: str, api_key: Optional[str] = None) -> dict:
        """Test if a connection is working."""
        p = self._get_provider(provider, endpoint, api_key)
        connected = p.is_available()
        models = p.list_models() if connected else []
        return {
            "connected": connected,
            "models": [self._model_to_dict(m) for m in models],
        }

    def list_remote_models(self, provider: str, endpoint: str, api_key: Optional[str] = None) -> list[dict]:
        """List available remote models."""
        p = self._get_provider(provider, endpoint, api_key)
        models = p.list_models()
        return [self._model_to_dict(m) for m in models]

    @staticmethod
    def _model_to_dict(m) -> dict:
        return {
            "id": m.id,
            "name": m.name,
            "size": m.size,
            "parameter_size": m.parameter_size,
            "quantization": m.quantization,
            "capabilities": m.capabilities,
        }

    def _get_provider(self, provider: str, endpoint: str, api_key: Optional[str] = None):
        """Get provider instance."""
        if provider == "ollama":
            from app.engine.ai.remote.ollama import OllamaProvider
            return OllamaProvider(endpoint, api_key)
        if provider == "openai":
            from app.engine.ai.remote.openai import OpenAIProvider
            return OpenAIProvider(endpoint, api_key)
        if provider == "gemini":
            from app.engine.ai.remote.gemini import GeminiProvider
            return GeminiProvider(endpoint, api_key)
        raise ValueError(f"Unknown provider: {provider}")

    def get_provider_for_connection(self, conn_id: Optional[int], provider: str):
        """Get provider instance from conn_id; returns None if conn_id is None."""
        if conn_id is not None:
            conn = self._dao.get_by_id(conn_id)
            if conn:
                return self._get_provider(conn.provider, conn.endpoint, conn.api_key)
        # fallback: get the first active connection of this provider
        conns = self._dao.get_by_provider(provider)
        for c in conns:
            if c.is_active:
                return self._get_provider(c.provider, c.endpoint, c.api_key)
        return None
