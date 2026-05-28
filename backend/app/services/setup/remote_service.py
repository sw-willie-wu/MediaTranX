"""
Remote API connection management service.
Manages external AI API connection settings (Ollama, OpenAI, Gemini).
"""
import logging
from typing import Optional

from app.adapters.security.secret_cipher import get_secret_cipher, SecretDecryptError
from app.db.dao.api_connection_dao import ApiConnectionDAO

logger = logging.getLogger(__name__)


class RemoteService:
    """Remote AI API connection management (Ollama, OpenAI, Gemini)."""

    def __init__(self):
        self._dao = ApiConnectionDAO()
        logger.info("RemoteService initialized")

    def get_connections(self, provider: Optional[str] = None) -> list[dict]:
        """Get connection list.

        SECURITY: the plaintext ``api_key`` is stripped from every connection
        and replaced with a ``has_api_key`` boolean. The key must never travel
        to the client — it stays server-side and is resolved by conn_id when a
        provider call is made (see list_remote_models_by_conn /
        get_provider_for_connection). Leaking it to the frontend is what let it
        end up in request URLs → uvicorn access logs in plaintext.
        """
        if provider:
            conns = self._dao.get_by_provider(provider)
        else:
            conns = self._dao.get_all()
        return [self._redact(c.model_dump()) for c in conns]

    def _redact(self, conn_dict: dict) -> dict:
        """Strip the stored api_key from a serialized connection, replacing it
        with ``has_api_key`` (bool) and ``key_hint`` (last-4 chars of plaintext
        or ``None``). Applied to EVERY connection that crosses the API boundary
        (get / add / update) so the raw key never travels to the client."""
        stored = conn_dict.pop("api_key", None)
        conn_dict["has_api_key"] = bool(stored)
        if not stored:
            conn_dict["key_hint"] = None
            return conn_dict
        try:
            plain = get_secret_cipher().decrypt(stored)
            conn_dict["key_hint"] = ("…" + plain[-4:]) if len(plain) >= 4 else "…"
        except SecretDecryptError:
            conn_dict["key_hint"] = "⚠ undecryptable"
        return conn_dict

    def add_connection(
        self,
        provider: str,
        name: str,
        endpoint: str,
        api_key: Optional[str] = None,
    ) -> dict:
        """Add a new connection."""
        if api_key:
            api_key = get_secret_cipher().encrypt(api_key)
        conn = self._dao.create(
            provider=provider,
            name=name,
            endpoint=endpoint,
            api_key=api_key,
        )
        return self._redact(conn.model_dump())

    def update_connection(self, conn_id: int, **kwargs) -> dict:
        """Update a connection. Raises NotFoundError if conn_id is unknown."""
        from app.handler.exceptions import NotFoundError

        if kwargs.get("api_key"):
            kwargs["api_key"] = get_secret_cipher().encrypt(kwargs["api_key"])
        conn = self._dao.update(conn_id, **kwargs)
        if conn is None:
            raise NotFoundError(f"Connection not found: {conn_id}")
        return self._redact(conn.model_dump())

    def delete_connection(self, conn_id: int) -> None:
        """Delete a connection. Raises NotFoundError if conn_id is unknown."""
        from app.handler.exceptions import NotFoundError

        if not self._dao.delete(conn_id):
            raise NotFoundError(f"Connection not found: {conn_id}")

    def test_connection(self, provider: str, endpoint: str, api_key: Optional[str] = None) -> dict:
        """Test if a connection is working."""
        p = self._get_provider(provider, endpoint, api_key)
        connected = p.is_available()
        models = p.list_models() if connected else []
        return {
            "connected": connected,
            "models": [self._model_to_dict(m) for m in models],
        }

    def list_remote_models_by_conn(self, conn_id: int) -> list[dict]:
        """List models for a SAVED connection, resolving the api_key
        server-side from conn_id. The caller (and the request URL) never sees
        the key. Raises NotFoundError when conn_id is unknown."""
        conn = self._dao.get_by_id(conn_id)
        if conn is None:
            from app.handler.exceptions import NotFoundError
            raise NotFoundError(f"Connection not found: {conn_id}")
        p = self._get_provider(conn.provider, conn.endpoint, conn.api_key)
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
            from app.adapters.ai.remote.ollama import OllamaProvider
            return OllamaProvider(endpoint, api_key)
        if provider == "openai":
            from app.adapters.ai.remote.openai import OpenAIProvider
            return OpenAIProvider(endpoint, api_key)
        if provider == "gemini":
            from app.adapters.ai.remote.gemini import GeminiProvider
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
            if c.enabled:
                return self._get_provider(c.provider, c.endpoint, c.api_key)
        return None
