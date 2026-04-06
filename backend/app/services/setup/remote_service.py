"""
Remote API 連線管理服務
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
管理外部 AI API 的連線設定（Ollama、OpenAI、Gemini）。
"""
import logging
from typing import Optional

from app.db.dao.api_connection_dao import ApiConnectionDAO

logger = logging.getLogger(__name__)


class RemoteService:
    """Remote API 連線管理服務"""

    def __init__(self):
        self._dao = ApiConnectionDAO()
        logger.info("RemoteService initialized")

    def get_connections(self, provider: Optional[str] = None) -> list[dict]:
        """取得連線列表"""
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
        """新增連線"""
        conn = self._dao.create(
            provider=provider,
            name=name,
            endpoint=endpoint,
            api_key=api_key,
        )
        return conn.model_dump()

    def update_connection(self, conn_id: int, **kwargs) -> Optional[dict]:
        """更新連線"""
        conn = self._dao.update(conn_id, **kwargs)
        return conn.model_dump() if conn else None

    def delete_connection(self, conn_id: int) -> bool:
        """刪除連線"""
        return self._dao.delete(conn_id)

    def test_connection(self, provider: str, endpoint: str, api_key: Optional[str] = None) -> dict:
        """測試連線是否正常"""
        p = self._get_provider(provider, endpoint, api_key)
        connected = p.is_available()
        models = p.list_models() if connected else []
        return {
            "connected": connected,
            "models": [self._model_to_dict(m) for m in models],
        }

    def list_remote_models(self, provider: str, endpoint: str, api_key: Optional[str] = None) -> list[dict]:
        """列舉遠端可用模型"""
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
        """取得 provider 實例"""
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

    def translate_text(
        self,
        text: str,
        target_lang: str,
        source_lang: str = "",
        provider: str = "",
        conn_id: Optional[int] = None,
        model_id: str = "",
    ) -> str:
        """透過雲端 API 翻譯文字"""
        from app.utils.prompts import build_translate_prompt

        prov = self.get_provider_for_connection(conn_id, provider)
        if prov is None:
            raise RuntimeError(f"找不到可用的 {provider} 連線")

        logger.info(f"translate_text: provider={provider}, conn_id={conn_id}, model_id={model_id}")

        prompt = build_translate_prompt(text, source_lang, target_lang)
        messages = [
            {"role": "system", "content": "You are a professional translator."},
            {"role": "user", "content": prompt},
        ]
        return prov.chat(model=model_id, messages=messages)

    def get_provider_for_connection(self, conn_id: Optional[int], provider: str):
        """從 conn_id 取得 provider 實例，如果 conn_id 為 None 則回傳 None"""
        if conn_id is not None:
            conn = self._dao.get_by_id(conn_id)
            if conn:
                return self._get_provider(conn.provider, conn.endpoint, conn.api_key)
        # fallback: 從所有啟用的該 provider 連線取第一個
        conns = self._dao.get_by_provider(provider)
        for c in conns:
            if c.is_active:
                return self._get_provider(c.provider, c.endpoint, c.api_key)
        return None
