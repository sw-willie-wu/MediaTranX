"""
Google Gemini Provider
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
透過 Google Gemini REST API 存取 Gemini 系列模型。
API 文件：https://ai.google.dev/api
"""
from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from typing import Optional

from .base import RemoteProvider, RemoteModel

logger = logging.getLogger(__name__)

DEFAULT_GEMINI_ENDPOINT = "https://generativelanguage.googleapis.com"

# ── 過濾規則 ──
# 只保留通用 LLM 模型，排除特殊用途和重複變體
#
# 保留的模型：
#   gemini-3.1-pro-preview        (text, vision)
#   gemini-3-flash-preview        (text, vision)
#   gemini-2.5-flash              (text, vision)
#   gemini-2.5-pro                (text, vision)
#
# 排除的模型：
#   *-image-*                     圖片生成（非 LLM）
#   *-native-audio-*              語音對話
#   *-tts*                        語音合成
#   *-lite*                       精簡版（有主版本就夠）
#   *-computer-use-*              UI 自動化
#   *embedding*                   向量嵌入
#   *deep-research*               研究 agent
#   *robotics*                    機器人
#   *veo*                         影片生成
#   *lyria*                       音樂生成
#   *imagen*                      圖片生成
#   *custom-tools*                工具特化版
#   *aqa*, *bisheng*, *text-*     舊版/內部模型
_HIDDEN_KEYWORDS = [
    "embedding", "aqa", "bisheng", "text-",
    "-image-", "-image", "imagen",
    "native-audio", "tts",
    "-lite", "custom-tools",
    "computer-use", "deep-research",
    "robotics", "veo", "lyria",
]


class GeminiProvider(RemoteProvider):
    """
    Google Gemini REST API Provider

    支援：
    - 連線檢查（GET /v1beta/models）
    - 模型列舉（GET /v1beta/models）
    - 文字對話（POST /v1beta/models/{model}:generateContent）
    """

    def __init__(self, endpoint: str = DEFAULT_GEMINI_ENDPOINT, api_key: Optional[str] = None):
        super().__init__(endpoint, api_key)

    def _api_url(self, path: str) -> str:
        """建立帶 API key 的 URL"""
        sep = "&" if "?" in path else "?"
        return f"{self.endpoint}{path}{sep}key={self.api_key}" if self.api_key else f"{self.endpoint}{path}"

    def connect(self) -> bool:
        """檢查 API key 是否有效"""
        try:
            url = self._api_url("/v1beta/models?pageSize=1")
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read())
                count = len(data.get("models", []))
                logger.info(f"Gemini connected: API key valid, {count}+ models at {self.endpoint}")
                return True
        except urllib.error.HTTPError as e:
            logger.warning(f"Gemini auth failed ({e.code})")
            return False
        except (urllib.error.URLError, OSError) as e:
            logger.warning(f"Gemini connection failed: {e}")
            return False

    def list_models(self) -> list[RemoteModel]:
        """列舉可用模型（分頁取全部）"""
        try:
            all_models: list[dict] = []
            page_token = ""

            while True:
                token_param = f"&pageToken={page_token}" if page_token else ""
                url = self._api_url(f"/v1beta/models?pageSize=100{token_param}")
                req = urllib.request.Request(url, method="GET")
                with urllib.request.urlopen(req, timeout=15) as resp:
                    data = json.loads(resp.read())

                all_models.extend(data.get("models", []))
                page_token = data.get("nextPageToken", "")
                if not page_token:
                    break

            # 過濾 + 去重
            seen: dict[str, RemoteModel] = {}
            for m in all_models:
                name = m.get("name", "")  # e.g. "models/gemini-2.0-flash"
                model_id = name.replace("models/", "")

                model_lower = model_id.lower()

                # 過濾特殊用途變體
                if any(kw in model_lower for kw in _HIDDEN_KEYWORDS):
                    continue

                # 去重：去掉版本/日期後綴
                family_key = self._model_family_key(model_id)
                if family_key in seen:
                    continue

                methods = m.get("supportedGenerationMethods", [])
                caps = self._methods_to_capabilities(model_id, methods)

                seen[family_key] = RemoteModel(
                    id=model_id,
                    name=m.get("displayName", model_id),
                    capabilities=caps,
                )

            return list(seen.values())

        except (urllib.error.URLError, urllib.error.HTTPError, OSError, json.JSONDecodeError) as e:
            logger.error(f"Failed to list Gemini models: {e}")
            return []

    def chat(
        self,
        model: str,
        messages: list[dict],
        max_tokens: int = 2048,
        temperature: float = 0.1,
    ) -> str:
        """Gemini generateContent"""
        # 轉換 messages 到 Gemini 格式
        contents = []
        for msg in messages:
            role = "user" if msg["role"] == "user" else "model"
            parts = []
            content = msg.get("content", "")

            if isinstance(content, str):
                parts.append({"text": content})
            elif isinstance(content, list):
                # 支援多部分 content（text + image）
                for part in content:
                    if part.get("type") == "text":
                        parts.append({"text": part["text"]})
                    elif part.get("type") == "image":
                        # 自訂格式：{"type": "image", "mime_type": ..., "data": base64}
                        parts.append({
                            "inline_data": {
                                "mime_type": part["mime_type"],
                                "data": part["data"],
                            }
                        })

            contents.append({"role": role, "parts": parts})

        payload = {
            "contents": contents,
            "generationConfig": {
                "maxOutputTokens": max_tokens,
                "temperature": temperature,
            },
        }

        url = self._api_url(f"/v1beta/models/{model}:generateContent")
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url, data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=300) as resp:
                result = json.loads(resp.read())
                candidates = result.get("candidates", [])
                if candidates:
                    parts = candidates[0].get("content", {}).get("parts", [])
                    return parts[0].get("text", "").strip() if parts else ""
                return ""
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            raise self._parse_error(e.code, body)
        except (urllib.error.URLError, OSError) as e:
            from app.handler.exceptions import RemoteApiError
            raise RemoteApiError("connection_failed", f"Gemini: {e}")

    @staticmethod
    def _parse_error(status: int, body: str):
        """解析 Gemini API 錯誤，回傳 RemoteApiError"""
        from app.handler.exceptions import RemoteApiError
        body_lower = body.lower()
        if status == 429 or "quota" in body_lower or "resource_exhausted" in body_lower:
            return RemoteApiError("quota_exceeded", body[:200])
        if status == 401 or status == 403 or "api_key" in body_lower:
            return RemoteApiError("auth_failed", body[:200])
        if status == 404:
            return RemoteApiError("model_not_found", body[:200])
        if status == 400:
            return RemoteApiError("invalid_request", body[:200])
        return RemoteApiError("remote_error", f"Gemini {status}: {body[:200]}")

    @staticmethod
    def _methods_to_capabilities(model_id: str, methods: list[str]) -> list[str]:
        """
        從 supportedGenerationMethods 推斷 capabilities

        常見 methods：
        - generateContent → text
        - generateMessage → text (legacy)
        - embedContent → embedding
        """
        caps = []

        if "generateContent" in methods or "generateMessage" in methods:
            caps.append("text")

        if "embedContent" in methods or "embedText" in methods:
            caps.append("embedding")

        # Gemini Pro Vision / Flash 等支援圖片
        model_lower = model_id.lower()
        if any(kw in model_lower for kw in ["flash", "pro", "ultra", "2.0", "2.5"]):
            if "text" in caps:
                caps.append("vision")

        if not caps:
            caps = ["text"]

        return caps

    @staticmethod
    def _model_family_key(model_id: str) -> str:
        """去掉版本/日期後綴：
        gemini-2.0-flash-001 → gemini-2.0-flash
        gemini-3.1-pro-preview-05-20 → gemini-3.1-pro-preview
        """
        import re
        # 去掉尾部的 -001 或 -05-20 日期後綴
        key = re.sub(r'-\d{2,4}(-\d{2}){0,2}$', '', model_id)
        return key


# ═══════════════════════════════════════════════════════════
# 單例工廠函數
# ═══════════════════════════════════════════════════════════
_gemini: Optional[GeminiProvider] = None


def get_gemini_provider(
    endpoint: str = DEFAULT_GEMINI_ENDPOINT,
    api_key: Optional[str] = None,
) -> GeminiProvider:
    """取得 GeminiProvider 單例"""
    global _gemini
    if _gemini is None or _gemini.endpoint != endpoint or _gemini.api_key != api_key:
        _gemini = GeminiProvider(endpoint, api_key)
    return _gemini
