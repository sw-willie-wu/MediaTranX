"""
OpenAI Provider
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Access GPT-series models via OpenAI REST API.
API docs: https://platform.openai.com/docs/api-reference
"""
from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from typing import Optional

from .base import RemoteProvider, RemoteModel

logger = logging.getLogger(__name__)

DEFAULT_OPENAI_ENDPOINT = "https://api.openai.com"

# Known model capabilities table (used first)
_KNOWN_MODELS: dict[str, list[str]] = {
    # GPT-5
    "gpt-5": ["text", "vision", "tools"],
    "gpt-5-pro": ["text", "vision", "tools"],
    # GPT-4o series (vision + tools)
    "gpt-4o": ["text", "vision", "tools"],
    "gpt-4o-mini": ["text", "vision", "tools"],
    "gpt-4o-audio-preview": ["text", "vision", "tools"],
    "gpt-4o-search-preview": ["text", "tools"],
    # GPT-4 Turbo（vision + tools）
    "gpt-4-turbo": ["text", "vision", "tools"],
    "gpt-4-turbo-preview": ["text", "tools"],
    # GPT-4（text only）
    "gpt-4": ["text", "tools"],
    # GPT-3.5
    "gpt-3.5-turbo": ["text", "tools"],
    # o series (reasoning)
    "o1": ["text", "vision", "tools"],
    "o1-mini": ["text", "tools"],
    "o1-preview": ["text"],
    "o3": ["text", "vision", "tools"],
    "o3-mini": ["text", "tools"],
    "o4-mini": ["text", "vision", "tools"],
    # Image models
    "chatgpt-image": ["text", "vision"],
    "gpt-image": ["text", "vision"],
    # Embedding
    "text-embedding-3-small": ["embedding"],
    "text-embedding-3-large": ["embedding"],
    "text-embedding-ada-002": ["embedding"],
}

# Hidden deprecated/unused models
_HIDDEN_MODELS = {"babbage-002", "davinci-002", "dall-e-2", "dall-e-3",
                  "tts-1", "tts-1-hd", "whisper-1", "canary-tts",
                  "codex-mini-latest"}

# Hidden special-purpose variants (filtered if keyword is present)
_HIDDEN_KEYWORDS = ["-preview", "transcribe", "tts", "instruct", "diarize"]


class OpenAIProvider(RemoteProvider):
    """
    OpenAI REST API Provider

    Supports:
    - Connection check (GET /v1/models)
    - Model listing (GET /v1/models)
    - Text chat (POST /v1/chat/completions)
    """

    def __init__(self, endpoint: str = DEFAULT_OPENAI_ENDPOINT, api_key: Optional[str] = None):
        super().__init__(endpoint, api_key)

    def _make_request(self, path: str, method: str = "GET", data: Optional[dict] = None, timeout: int = 10):
        """Build a request with Authorization header."""
        url = f"{self.endpoint}{path}"
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        body = json.dumps(data).encode("utf-8") if data else None
        req = urllib.request.Request(url, data=body, headers=headers, method=method)
        return urllib.request.urlopen(req, timeout=timeout)

    def connect(self) -> bool:
        """Check if the API key is valid."""
        try:
            with self._make_request("/v1/models", timeout=10) as resp:
                data = json.loads(resp.read())
                count = len(data.get("data", []))
                logger.info(f"OpenAI connected: {count} models available at {self.endpoint}")
                return True
        except urllib.error.HTTPError as e:
            logger.warning(f"OpenAI auth failed ({e.code}): invalid API key or endpoint")
            return False
        except (urllib.error.URLError, OSError) as e:
            logger.warning(f"OpenAI connection failed: {e}")
            return False

    def list_models(self) -> list[RemoteModel]:
        """List available models."""
        try:
            with self._make_request("/v1/models", timeout=15) as resp:
                data = json.loads(resp.read())

            # Deduplicate: keep only one per family (prefer base version without date suffix)
            seen_families: dict[str, RemoteModel] = {}
            for m in data.get("data", []):
                model_id = m.get("id", "")
                if model_id in _HIDDEN_MODELS:
                    continue
                if any(kw in model_id for kw in _HIDDEN_KEYWORDS):
                    continue
                caps = self._detect_capabilities(model_id)

                family_key = self._model_family_key(model_id)
                existing = seen_families.get(family_key)
                if existing is None or self._is_preferred_variant(model_id, existing.id):
                    seen_families[family_key] = RemoteModel(
                        id=model_id,
                        name=model_id,
                        family=m.get("owned_by"),
                        capabilities=caps,
                    )

            return list(seen_families.values())

        except (urllib.error.URLError, urllib.error.HTTPError, OSError, json.JSONDecodeError) as e:
            logger.error(f"Failed to list OpenAI models: {e}")
            return []

    def chat(
        self,
        model: str,
        messages: list[dict],
        max_tokens: int = 2048,
        temperature: float = 0.1,
    ) -> str:
        """OpenAI chat -- auto-select Chat Completions or Responses API."""
        if self._needs_responses_api(model):
            return self._chat_responses(model, messages, max_tokens)
        return self._chat_completions(model, messages, max_tokens, temperature)

    def _chat_completions(self, model: str, messages: list[dict], max_tokens: int, temperature: float) -> str:
        """POST /v1/chat/completions"""
        # GPT-5+ uses max_completion_tokens, older models use max_tokens
        token_key = "max_completion_tokens" if self._is_new_model(model) else "max_tokens"
        payload = {
            "model": model,
            "messages": messages,
            token_key: max_tokens,
            "temperature": temperature,
        }
        try:
            with self._make_request("/v1/chat/completions", method="POST", data=payload, timeout=300) as resp:
                result = json.loads(resp.read())
                return result["choices"][0]["message"]["content"].strip()
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            raise self._parse_error(e.code, body)
        except (urllib.error.URLError, OSError) as e:
            from app.handler.exceptions import RemoteApiError
            raise RemoteApiError("connection_failed", f"OpenAI: {e}")

    def _chat_responses(self, model: str, messages: list[dict], max_tokens: int) -> str:
        """POST /v1/responses (for GPT-5.2 Pro and other pro/thinking models)."""
        # Responses API uses different content type format:
        # text -> input_text, image_url -> input_image
        converted = []
        for msg in messages:
            content = msg.get("content", "")
            if isinstance(content, str):
                converted.append({
                    "role": msg["role"],
                    "content": [{"type": "input_text", "text": content}],
                })
            elif isinstance(content, list):
                parts = []
                for part in content:
                    if part.get("type") == "text":
                        parts.append({"type": "input_text", "text": part["text"]})
                    elif part.get("type") == "image_url":
                        parts.append({
                            "type": "input_image",
                            "image_url": part["image_url"]["url"],
                        })
                    else:
                        parts.append(part)
                converted.append({"role": msg["role"], "content": parts})
            else:
                converted.append(msg)

        payload = {
            "model": model,
            "input": converted,
            "max_output_tokens": max_tokens,
        }
        try:
            with self._make_request("/v1/responses", method="POST", data=payload, timeout=600) as resp:
                result = json.loads(resp.read())
                # Responses API has a different response format
                output = result.get("output", [])
                for item in output:
                    if item.get("type") == "message":
                        for content in item.get("content", []):
                            if content.get("type") == "output_text":
                                return content.get("text", "").strip()
                # fallback
                return result.get("output_text", "").strip()
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            raise self._parse_error(e.code, body)
        except (urllib.error.URLError, OSError) as e:
            from app.handler.exceptions import RemoteApiError
            raise RemoteApiError("connection_failed", f"OpenAI: {e}")

    @staticmethod
    def _parse_error(status: int, body: str):
        """Parse OpenAI API error and return a RemoteApiError."""
        from app.handler.exceptions import RemoteApiError
        body_lower = body.lower()
        if status == 429 or "quota" in body_lower or "rate" in body_lower:
            return RemoteApiError("quota_exceeded", body[:200])
        if status == 401 or status == 403:
            return RemoteApiError("auth_failed", body[:200])
        if status == 404:
            if "not a chat model" in body_lower:
                return RemoteApiError("model_not_supported", body[:200])
            return RemoteApiError("model_not_found", body[:200])
        if status == 400:
            if "max_tokens" in body_lower or "max_completion_tokens" in body_lower:
                return RemoteApiError("invalid_params", body[:200])
            return RemoteApiError("invalid_request", body[:200])
        return RemoteApiError("remote_error", f"OpenAI {status}: {body[:200]}")

    @staticmethod
    def _needs_responses_api(model: str) -> bool:
        """Determine if the model requires the Responses API (pro/thinking models)."""
        m = model.lower()
        if "-pro" in m:
            return True
        if m.startswith("o1") or m.startswith("o3") or m.startswith("o4"):
            return True
        return False

    @staticmethod
    def _is_new_model(model: str) -> bool:
        """Determine if the model is new (uses max_completion_tokens instead of max_tokens)."""
        m = model.lower()
        # GPT-5+, o1+, o3+, o4+ all use the new parameter
        if m.startswith("gpt-5") or m.startswith("gpt-6"):
            return True
        if m.startswith("o1") or m.startswith("o3") or m.startswith("o4"):
            return True
        return False

    @staticmethod
    def _detect_capabilities(model_id: str) -> list[str]:
        """
        Infer capabilities from the known model table.

        Tries exact match first, then prefix match (gpt-4o-2024-11-20 -> gpt-4o).
        Unrecognized models default to ["text"].
        """
        model_lower = model_id.lower()

        # 1. Exact match
        if model_lower in _KNOWN_MODELS:
            return list(_KNOWN_MODELS[model_lower])

        # 2. Prefix match (sorted by key length descending, prefer more specific matches)
        for known, caps in sorted(_KNOWN_MODELS.items(), key=lambda x: -len(x[0])):
            if model_lower.startswith(known):
                return list(caps)

        # 3. Keyword fallback
        if "embedding" in model_lower or "embed" in model_lower:
            return ["embedding"]

        # Unrecognized models default to text
        return ["text"]

    @staticmethod
    def _model_family_key(model_id: str) -> str:
        """
        Extract model family key by stripping date suffixes and variants.

        gpt-4o-2024-11-20       -> gpt-4o
        gpt-3.5-turbo-0125      -> gpt-3.5-turbo
        gpt-3.5-turbo-16k       -> gpt-3.5-turbo
        gpt-3.5-turbo-instruct  -> gpt-3.5-turbo-instruct
        o4-mini-2025-04-16      -> o4-mini
        text-embedding-3-small  -> text-embedding-3-small (unchanged)
        """
        import re
        # Remove date suffixes: -YYYY-MM-DD or -YYMM or -MMDD
        cleaned = re.sub(r'-\d{4}-\d{2}-\d{2}$', '', model_id)
        cleaned = re.sub(r'-\d{4}$', '', cleaned)
        # Remove context-size variants like -16k
        cleaned = re.sub(r'-\d+k$', '', cleaned)
        return cleaned

    @staticmethod
    def _is_preferred_variant(candidate: str, existing: str) -> bool:
        """
        Determine if candidate is a better representative than existing.
        Prefers base versions without date suffixes (shorter = more base).
        """
        # Shorter = more base
        if len(candidate) < len(existing):
            return True
        # Same length: lexicographically later is usually newer
        if len(candidate) == len(existing):
            return candidate > existing
        return False


# ═══════════════════════════════════════════════════════════
# Singleton factory
# ═══════════════════════════════════════════════════════════
_openai: Optional[OpenAIProvider] = None


def get_openai_provider(
    endpoint: str = DEFAULT_OPENAI_ENDPOINT,
    api_key: Optional[str] = None,
) -> OpenAIProvider:
    """Get the OpenAIProvider singleton."""
    global _openai
    if _openai is None or _openai.endpoint != endpoint or _openai.api_key != api_key:
        _openai = OpenAIProvider(endpoint, api_key)
    return _openai
