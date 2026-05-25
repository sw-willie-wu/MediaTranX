"""
Google Gemini Provider
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Access Gemini-series models via Google Gemini REST API.
API docs: https://ai.google.dev/api
"""
from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from typing import Callable, Optional

from .base import RemoteProvider, RemoteModel

logger = logging.getLogger(__name__)

DEFAULT_GEMINI_ENDPOINT = "https://generativelanguage.googleapis.com"

# ── Filter rules ──
# Keep only general-purpose LLM models; exclude special-purpose and duplicate variants.
#
# Kept models:
#   gemini-3.1-pro-preview        (text, vision)
#   gemini-3-flash-preview        (text, vision)
#   gemini-2.5-flash              (text, vision)
#   gemini-2.5-pro                (text, vision)
#
# Excluded models:
#   *-image-*                     Image generation (not LLM)
#   *-native-audio-*              Voice conversation
#   *-tts*                        Text-to-speech
#   *-lite*                       Lite variant (main version suffices)
#   *-computer-use-*              UI automation
#   *embedding*                   Vector embedding
#   *deep-research*               Research agent
#   *robotics*                    Robotics
#   *veo*                         Video generation
#   *lyria*                       Music generation
#   *imagen*                      Image generation
#   *custom-tools*                Tool-specialized variant
#   *aqa*, *bisheng*, *text-*     Legacy/internal models
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

    Supports:
    - Connection check (GET /v1beta/models)
    - Model listing (GET /v1beta/models)
    - Text chat (POST /v1beta/models/{model}:generateContent)
    """

    PROVIDER_NAME = "gemini"
    IMAGE_PREP_MODE = "recompress"

    def __init__(self, endpoint: str = DEFAULT_GEMINI_ENDPOINT, api_key: Optional[str] = None):
        super().__init__(endpoint, api_key)

    def _api_url(self, path: str) -> str:
        """Build a URL with the API key."""
        sep = "&" if "?" in path else "?"
        return f"{self.endpoint}{path}{sep}key={self.api_key}" if self.api_key else f"{self.endpoint}{path}"

    def connect(self) -> bool:
        """Check if the API key is valid."""
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
        """List available models (paginated, fetches all)."""
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

            # Filter + deduplicate
            seen: dict[str, RemoteModel] = {}
            for m in all_models:
                name = m.get("name", "")  # e.g. "models/gemini-2.0-flash"
                model_id = name.replace("models/", "")

                model_lower = model_id.lower()

                # Filter out special-purpose variants
                if any(kw in model_lower for kw in _HIDDEN_KEYWORDS):
                    continue

                # Deduplicate: strip version/date suffixes
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

    def get_summary_chunking_hints(self, model: str) -> dict:
        """Gemini 1.5+ has 128k+ context (1.5-flash: 1M, 2.0-flash: 1M,
        2.5-flash: 1M). Use 128k / 24k — going larger doesn't help (output
        is still capped at 8192) and risks single-chunk latency exceeding our
        900s HTTP timeout on slower models.
        """
        return {"n_ctx": 128000, "model_cap": 24000}

    def _convert_to_gemini_contents(self, messages: list[dict]) -> list[dict]:
        """Convert OpenAI-shape messages to Gemini's contents shape.

        Used by both blocking and streaming chat paths.
        """
        contents = []
        for msg in messages:
            role = "user" if msg["role"] == "user" else "model"
            parts = []
            content = msg.get("content", "")
            if isinstance(content, str):
                parts.append({"text": content})
            elif isinstance(content, list):
                for part in content:
                    if part.get("type") == "text":
                        parts.append({"text": part["text"]})
                    elif part.get("type") == "image":
                        # build_vision_chat_messages produces type:"image",
                        # mime_type, data. Wire shape uses inline_data.
                        parts.append({
                            "inline_data": {
                                "mime_type": part["mime_type"],
                                "data": part["data"],
                            }
                        })
            contents.append({"role": role, "parts": parts})
        return contents

    def _build_generation_config(
        self, max_tokens: int, temperature: float, task: Optional[str]
    ) -> dict:
        """Build generationConfig dict, injecting thinkingConfig when needed.

        When task="frame_select", sets thinkingBudget=0 to disable Gemini
        2.5+ implicit thinking. Without this, thinking tokens silently
        consume the entire max_tokens budget (e.g., max_tokens=16 → 22
        thinking tokens + 0 visible output tokens), causing empty responses
        for frame_select. Production bug, 2026-05.
        """
        cfg: dict = {"maxOutputTokens": max_tokens, "temperature": temperature}
        if task == "frame_select":
            # Disable implicit thinking on Gemini 2.5+ — frame_select expects a
            # single numeric token, and thinking would silently consume the
            # entire max_tokens budget (production bug, 2026-05).
            cfg["thinkingConfig"] = {"thinkingBudget": 0}
        return cfg

    def chat(
        self,
        model: str,
        messages: list[dict],
        *,
        max_tokens: int = 2048,
        temperature: float = 0.1,
        abort_hook: Optional[Callable] = None,
        task: Optional[str] = None,
    ) -> str:
        """Gemini chat — dispatch by abort_hook presence."""
        if abort_hook is None:
            return self._chat_blocking(model, messages, max_tokens, temperature, task=task)
        return self._chat_streaming(model, messages, max_tokens, temperature, abort_hook, task=task)

    def _chat_blocking(
        self, model: str, messages: list[dict],
        max_tokens: int, temperature: float,
        *,
        task: Optional[str] = None,
    ) -> str:
        """Blocking generateContent (preserved behaviour for 5 legacy callers)."""
        contents = self._convert_to_gemini_contents(messages)
        payload = {
            "contents": contents,
            "generationConfig": self._build_generation_config(max_tokens, temperature, task),
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

    def _chat_streaming(
        self, model: str, messages: list[dict],
        max_tokens: int, temperature: float,
        abort_hook: Callable,
        *,
        task: Optional[str] = None,
    ) -> str:
        """streamGenerateContent?alt=sse — SSE parser + cancel-on-socket-close."""
        contents = self._convert_to_gemini_contents(messages)
        payload = {
            "contents": contents,
            "generationConfig": self._build_generation_config(max_tokens, temperature, task),
        }
        url = self._api_url(
            f"/v1beta/models/{model}:streamGenerateContent?alt=sse"
        )
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url, data=data,
            headers={
                "Content-Type": "application/json",
                "Accept": "text/event-stream",
            },
            method="POST",
        )

        from app.handler.exceptions import RemoteApiError
        resp = None
        try:
            # 180s socket timeout: cloud TTFT on large summarize chunks (~9k+
            # tokens with thinking) routinely exceeds 30s; cancel still works
            # via abort_hook → resp.close() from another thread, not timeout.
            resp = urllib.request.urlopen(req, timeout=180)
            abort_hook(resp)
            parts: list[str] = []
            for raw in resp:
                line = raw.strip()
                if not line.startswith(b"data: "):
                    continue
                payload_s = line[6:].decode("utf-8", errors="replace").strip()
                if not payload_s:
                    continue
                try:
                    obj = json.loads(payload_s)
                except json.JSONDecodeError:
                    continue
                cands = obj.get("candidates", [])
                if not cands:
                    continue
                cand0 = cands[0]
                for p in cand0.get("content", {}).get("parts", []):
                    t = p.get("text", "")
                    if t:
                        parts.append(t)
                fr = cand0.get("finishReason")
                if fr in ("SAFETY", "RECITATION", "BLOCKLIST",
                          "PROHIBITED_CONTENT", "SPII",
                          "IMAGE_SAFETY", "OTHER"):
                    raise RemoteApiError(
                        "safety_blocked",
                        f"Gemini blocked: finishReason={fr}, "
                        f"partial_output={''.join(parts)[:200]!r}",
                    )
            return "".join(parts).strip()
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            raise self._parse_error(e.code, body)
        except urllib.error.URLError as e:
            raise RemoteApiError("connection_failed", f"Gemini: {e}")
        except OSError as e:
            raise RemoteApiError("connection_failed", f"Gemini: {e}")
        finally:
            if resp is not None:
                try: resp.close()
                except Exception: pass

    @staticmethod
    def _parse_error(status: int, body: str):
        """Parse Gemini API error and return a RemoteApiError."""
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
        Infer capabilities from supportedGenerationMethods.

        Common methods:
        - generateContent -> text
        - generateMessage -> text (legacy)
        - embedContent -> embedding
        """
        caps = []

        if "generateContent" in methods or "generateMessage" in methods:
            caps.append("text")

        if "embedContent" in methods or "embedText" in methods:
            caps.append("embedding")

        # Gemini Pro Vision / Flash etc. support images
        model_lower = model_id.lower()
        if any(kw in model_lower for kw in ["flash", "pro", "ultra", "2.0", "2.5"]):
            if "text" in caps:
                caps.append("vision")

        if not caps:
            caps = ["text"]

        return caps

    @staticmethod
    def _model_family_key(model_id: str) -> str:
        """Strip version/date suffixes:
        gemini-2.0-flash-001 -> gemini-2.0-flash
        gemini-3.1-pro-preview-05-20 -> gemini-3.1-pro-preview
        """
        import re
        # Remove trailing -001 or -05-20 date suffixes
        key = re.sub(r'-\d{2,4}(-\d{2}){0,2}$', '', model_id)
        return key


# ═══════════════════════════════════════════════════════════
# Singleton factory
# ═══════════════════════════════════════════════════════════
_gemini: Optional[GeminiProvider] = None


def get_gemini_provider(
    endpoint: str = DEFAULT_GEMINI_ENDPOINT,
    api_key: Optional[str] = None,
) -> GeminiProvider:
    """Get the GeminiProvider singleton."""
    global _gemini
    if _gemini is None or _gemini.endpoint != endpoint or _gemini.api_key != api_key:
        _gemini = GeminiProvider(endpoint, api_key)
    return _gemini
