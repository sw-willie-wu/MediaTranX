"""
Ollama Provider
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
透過 Ollama REST API 存取本地或遠端 Ollama 服務。
API 文件：https://github.com/ollama/ollama/blob/main/docs/api.md
"""
from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from typing import Optional

from .base import RemoteProvider, RemoteModel

logger = logging.getLogger(__name__)

DEFAULT_OLLAMA_ENDPOINT = "http://localhost:11434"


class OllamaProvider(RemoteProvider):
    """
    Ollama REST API Provider

    支援：
    - 連線檢查（GET /api/version）
    - 模型列舉（GET /api/tags）
    - 文字對話（POST /api/chat）
    """

    def __init__(self, endpoint: str = DEFAULT_OLLAMA_ENDPOINT, api_key: Optional[str] = None):
        super().__init__(endpoint, api_key)
        self._caps_cache: dict[str, list[str]] = {}  # model_name → capabilities

    def connect(self) -> bool:
        """檢查 Ollama 服務是否運行"""
        try:
            req = urllib.request.Request(
                f"{self.endpoint}/api/version",
                method="GET",
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read())
                version = data.get("version", "unknown")
                logger.info(f"Ollama connected: v{version} at {self.endpoint}")
                return True
        except (urllib.error.URLError, OSError, json.JSONDecodeError) as e:
            logger.warning(f"Ollama connection failed: {e}")
            return False

    def list_models(self) -> list[RemoteModel]:
        """列舉 Ollama 已安裝的模型（含 capabilities 偵測）"""
        try:
            req = urllib.request.Request(
                f"{self.endpoint}/api/tags",
                method="GET",
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read())

            models = []
            for m in data.get("models", []):
                details = m.get("details", {})
                families = details.get("families") or []
                capabilities = self._detect_capabilities(m["name"], families)
                models.append(RemoteModel(
                    id=m["name"],
                    name=m["name"],
                    size=m.get("size"),
                    family=details.get("family"),
                    parameter_size=details.get("parameter_size"),
                    quantization=details.get("quantization_level"),
                    capabilities=capabilities,
                ))
            return models

        except (urllib.error.URLError, OSError, json.JSONDecodeError) as e:
            logger.error(f"Failed to list Ollama models: {e}")
            return []

    def _detect_capabilities(self, model_name: str, families: list[str]) -> list[str]:
        """
        偵測模型 capabilities

        透過 /api/show 的 capabilities 欄位取得（Ollama 原生支援）。
        Fallback: 從模型名稱和 families 推斷。
        """
        # 快取命中
        if model_name in self._caps_cache:
            return self._caps_cache[model_name]

        # 呼叫 /api/show 取得官方 capabilities
        try:
            payload = json.dumps({"name": model_name}).encode("utf-8")
            req = urllib.request.Request(
                f"{self.endpoint}/api/show",
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                info = json.loads(resp.read())
                ollama_caps = info.get("capabilities", [])
                if ollama_caps:
                    # Ollama 回傳格式：["completion", "vision", "tools", "thinking"]
                    # 轉換成我們的格式
                    caps = ["text"]
                    if "vision" in ollama_caps:
                        caps.append("vision")
                    if "embedding" in ollama_caps:
                        caps.append("embedding")
                    if "tools" in ollama_caps:
                        caps.append("tools")
                    self._caps_cache[model_name] = caps
                    return caps
        except Exception:
            pass

        # Fallback: 從名稱和 families 推斷
        caps = ["text"]
        name_lower = model_name.lower()
        if any(kw in name_lower for kw in ["vl", "vision", "llava", "bakllava", "moondream"]):
            caps.append("vision")
        if any(kw in name_lower for kw in ["embed", "nomic-embed", "mxbai-embed"]):
            caps.append("embedding")
        if any(f in families for f in ["clip", "mllama"]):
            if "vision" not in caps:
                caps.append("vision")

        self._caps_cache[model_name] = caps
        return caps

    def chat(
        self,
        model: str,
        messages: list[dict],
        max_tokens: int = 2048,
        temperature: float = 0.1,
    ) -> str:
        """
        Ollama chat completion

        Args:
            model: 模型名稱（例如 "llama3.2:3b"）
            messages: [{"role": "user", "content": "..."}]
        """
        payload = {
            "model": model,
            "messages": messages,
            "stream": False,
            "options": {
                "num_predict": max_tokens,
                "temperature": temperature,
            },
        }

        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"{self.endpoint}/api/chat",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=300) as resp:
                result = json.loads(resp.read())
                content = result.get("message", {}).get("content", "")
                return content.strip()
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            raise self._parse_error(e.code, body)
        except urllib.error.URLError as e:
            from app.exceptions import RemoteApiError
            raise RemoteApiError("connection_failed", f"Ollama: {e}")
        except OSError as e:
            from app.exceptions import RemoteApiError
            raise RemoteApiError("connection_failed", f"Ollama: {e}")

    @staticmethod
    def _parse_error(status: int, body: str):
        """解析 Ollama API 錯誤，回傳 RemoteApiError"""
        from app.exceptions import RemoteApiError
        body_lower = body.lower()
        if status == 500 and ("eof" in body_lower or "load" in body_lower):
            return RemoteApiError("gpu_oom", f"Ollama 500: {body[:200]}")
        if status == 404 or "not found" in body_lower:
            return RemoteApiError("model_not_found", body[:200])
        if status == 401 or status == 403:
            return RemoteApiError("auth_failed", body[:200])
        return RemoteApiError("remote_error", f"Ollama {status}: {body[:200]}")

    def pull_model(self, model_name: str, on_progress: Optional[callable] = None) -> bool:
        """
        拉取模型（ollama pull）

        Args:
            model_name: 模型名稱（例如 "llama3.2:3b"）
            on_progress: 進度回調 (completed_bytes, total_bytes)

        Returns:
            True 如果成功
        """
        payload = {
            "name": model_name,
            "stream": True,
        }

        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"{self.endpoint}/api/pull",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=600) as resp:
                for line in resp:
                    try:
                        status = json.loads(line)
                        if on_progress and "completed" in status and "total" in status:
                            on_progress(status["completed"], status["total"])
                        if status.get("status") == "success":
                            logger.info(f"Ollama model pulled: {model_name}")
                            return True
                    except json.JSONDecodeError:
                        continue
            return True
        except Exception as e:
            logger.error(f"Failed to pull Ollama model {model_name}: {e}")
            return False


# ═══════════════════════════════════════════════════════════
# 單例工廠函數
# ═══════════════════════════════════════════════════════════
_ollama: Optional[OllamaProvider] = None


def get_ollama_provider(endpoint: str = DEFAULT_OLLAMA_ENDPOINT) -> OllamaProvider:
    """取得 OllamaProvider 單例"""
    global _ollama
    if _ollama is None or _ollama.endpoint != endpoint:
        _ollama = OllamaProvider(endpoint)
    return _ollama
