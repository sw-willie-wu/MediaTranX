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
import uuid
from typing import Callable, Iterator, Optional

from app.adapters.ai.remote import _http
from .base import RemoteProvider, RemoteModel, PROBE_TIMEOUT

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
    # `-lite` removed — Flash Lite variants are legitimate, cheaper picks for
    # the agent (separate quota bucket from Flash). Users picking Gemini for
    # the agent want all callable variants in the picker.
    "custom-tools",
    "computer-use", "deep-research",
    "robotics", "veo", "lyria",
]

# ── Gemini ↔ OpenAI conversion helpers ─────────────────────────────────────

_GEMINI_TYPES = {
    "object": "OBJECT",
    "array": "ARRAY",
    "string": "STRING",
    "number": "NUMBER",
    "integer": "INTEGER",
    "boolean": "BOOLEAN",
}


def _convert_jsonschema_to_gemini(schema: dict) -> dict:
    """Recursively convert a JSONSchema dict to Gemini's restricted subset.

    - Type names are uppercased (e.g. "object" → "OBJECT").
    - Nested ``properties`` and ``items`` are recursively converted.
    - Unsupported combiners (``oneOf``, ``anyOf``, ``allOf``) are dropped
      with a warning; Gemini's function-declaration schema does not support
      them.
    - Unrecognised keys (``title``, ``examples``, ``$schema``, …) are
      silently dropped to keep the declaration clean.
    """
    result: dict = {}
    t = schema.get("type")
    if t and t in _GEMINI_TYPES:
        result["type"] = _GEMINI_TYPES[t]
    if "description" in schema:
        result["description"] = schema["description"]
    if "enum" in schema:
        result["enum"] = schema["enum"]
    if "required" in schema:
        result["required"] = schema["required"]
    if "properties" in schema:
        result["properties"] = {
            k: _convert_jsonschema_to_gemini(v)
            for k, v in schema["properties"].items()
        }
    if "items" in schema:
        result["items"] = _convert_jsonschema_to_gemini(schema["items"])
    for unsupported in ("oneOf", "anyOf", "allOf"):
        if unsupported in schema:
            logger.warning("Gemini tools: dropping unsupported '%s' from schema", unsupported)
    return result


def _to_gemini_tools(tools: list[dict]) -> list[dict]:
    """Convert OpenAI-flat tool definitions to a Gemini ``functionDeclarations`` block.

    Input shape (each tool)::

        {"name": str, "description": str, "parameters": {JSONSchema}}

    Output shape::

        [{"functionDeclarations": [{"name": str, "description": str,
                                    "parameters": {GeminiSchema}}, ...]}]

    Returns an empty list when ``tools`` is falsy.
    """
    if not tools:
        return []
    declarations = []
    for t in tools:
        declarations.append({
            "name": t["name"],
            "description": t.get("description", ""),
            "parameters": _convert_jsonschema_to_gemini(t.get("parameters", {})),
        })
    return [{"functionDeclarations": declarations}]


def _to_gemini_messages(messages: list[dict]) -> tuple[str | None, list[dict]]:
    """Convert OpenAI-shaped messages to Gemini ``contents`` + optional ``systemInstruction``.

    OpenAI role mapping:
    - ``system``    → extracted as the system instruction (not placed in contents)
    - ``user``      → ``role="user"``, text parts
    - ``assistant`` → ``role="model"``, optional text + optional functionCall parts
    - ``tool``      → ``role="function"``, functionResponse part
                      (the tool name is looked up from the preceding assistant message)

    Returns ``(system_instruction_text | None, contents_list)``.
    """
    # Build a lookup: toolCallId → function name from all prior assistant messages.
    tool_call_id_to_name: dict[str, str] = {}
    for m in messages:
        if m.get("role") == "assistant":
            for tc in m.get("toolCalls") or m.get("tool_calls") or []:
                tc_id = tc.get("id", "")
                name = (tc.get("function") or {}).get("name", "")
                if tc_id and name:
                    tool_call_id_to_name[tc_id] = name

    contents: list[dict] = []
    system_instruction: str | None = None

    for m in messages:
        role = m.get("role")

        if role == "system":
            system_instruction = m.get("content", "")
            continue

        if role == "user":
            contents.append({
                "role": "user",
                "parts": [{"text": m.get("content", "")}],
            })

        elif role == "assistant":
            parts: list[dict] = []
            if m.get("content"):
                parts.append({"text": m["content"]})
            for tc in m.get("toolCalls") or m.get("tool_calls") or []:
                fn = tc.get("function") or {}
                try:
                    args = json.loads(fn.get("arguments") or "{}")
                except (json.JSONDecodeError, TypeError):
                    args = {}
                parts.append({"functionCall": {
                    "name": fn.get("name", ""),
                    "args": args,
                }})
            if parts:
                contents.append({"role": "model", "parts": parts})

        elif role == "tool":
            tc_id = m.get("toolCallId") or m.get("tool_call_id") or ""
            tool_name = tool_call_id_to_name.get(tc_id, "unknown_tool")
            raw_content = m.get("content", "{}")
            try:
                response = json.loads(raw_content)
                if not isinstance(response, dict):
                    response = {"content": response}
            except (json.JSONDecodeError, TypeError):
                response = {"content": raw_content}
            contents.append({
                "role": "function",
                "parts": [{"functionResponse": {
                    "name": tool_name,
                    "response": response,
                }}],
            })

    return system_instruction, contents


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

    def connect(self, timeout: int = PROBE_TIMEOUT) -> bool:
        """Check if the API key is valid."""
        try:
            url = self._api_url("/v1beta/models?pageSize=1")
            req = urllib.request.Request(url, method="GET")
            with _http.urlopen(req, timeout=timeout) as resp:
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

    def list_models(self, timeout: int = PROBE_TIMEOUT) -> list[RemoteModel]:
        """List available models (paginated, fetches all)."""
        from app.handler.exceptions import RemoteApiError
        try:
            all_models: list[dict] = []
            page_token = ""

            while True:
                token_param = f"&pageToken={page_token}" if page_token else ""
                url = self._api_url(f"/v1beta/models?pageSize=100{token_param}")
                req = urllib.request.Request(url, method="GET")
                with _http.urlopen(req, timeout=timeout) as resp:
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

        except urllib.error.HTTPError as e:
            body = ""
            try:
                body = e.read().decode("utf-8", "replace")
            except Exception:
                pass
            logger.warning(f"Gemini list_models HTTP {e.code}: {body[:200]}")
            raise self._parse_error(e.code, body)
        except (urllib.error.URLError, OSError) as e:
            logger.warning(f"Gemini list_models connection failed: {e}")
            raise RemoteApiError("connection_failed", f"Gemini: {e}")
        except json.JSONDecodeError as e:
            logger.warning(f"Gemini list_models bad JSON: {e}")
            raise RemoteApiError("remote_error", f"Gemini: invalid response ({e})")

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
            with _http.urlopen(req, timeout=300) as resp:
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
            resp = _http.urlopen(req, timeout=180)
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

    def chat_completions_stream(
        self,
        *,
        model: str,
        messages: list[dict],
        tools: list[dict] | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.1,
        abort_hook: Optional[Callable] = None,
    ) -> Iterator[dict]:
        """Yield OpenAI-compat normalised chunks translated from Gemini's
        ``streamGenerateContent?alt=sse`` response.

        Each yielded chunk matches the shape expected by
        ``_parse_openai_compat_chunk`` in ``chat_service.py``:

        Text delta::

            {"id": "<run_id>", "choices": [{"delta": {"content": "<text>"}}]}

        Tool-call delta::

            {"id": "<run_id>", "choices": [{"delta": {"tool_calls": [
                {"index": int, "id": str, "function": {"name": str,
                                                        "arguments": str}}
            ]}}]}

        Final usage chunk (when Gemini returns ``usageMetadata``)::

            {"choices": [], "usage": {"prompt_tokens": int,
                                       "completion_tokens": int,
                                       "total_tokens": int}}

        This method does NOT raise ``RemoteApiError`` for safety finish reasons
        (that is only needed for the legacy ``chat()`` path which accumulates
        a string result).  The caller — ``RemoteChatSession.stream()`` — handles
        stream closure naturally.

        Args:
            tools:      Optional OpenAI-flat tool definitions; forwarded as
                        Gemini ``functionDeclarations``.
            abort_hook: Invoked exactly once immediately after ``urlopen``
                        returns (before reading any lines).  Lets
                        ``RemoteChatSession`` stash the response object so
                        ``kill_process()`` can close it from another thread.
        """
        system_instruction, contents = _to_gemini_messages(messages)
        gemini_tools = _to_gemini_tools(tools) if tools else []

        payload: dict = {
            "contents": contents,
            "generationConfig": {
                "maxOutputTokens": max_tokens,
                "temperature": temperature,
            },
        }
        if system_instruction:
            payload["systemInstruction"] = {"parts": [{"text": system_instruction}]}
        if gemini_tools:
            payload["tools"] = gemini_tools

        url = self._api_url(
            f"/v1beta/models/{model}:streamGenerateContent?alt=sse"
        )
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Accept": "text/event-stream",
            },
            method="POST",
        )

        resp = None
        try:
            # 180s socket timeout: cancel arrives via abort_hook → resp.close()
            # from another thread, not timeout.
            resp = _http.urlopen(req, timeout=180)
        except urllib.error.HTTPError as e:
            body_err = e.read().decode("utf-8", errors="replace")[:200]
            raise self._parse_error(e.code, body_err)
        except (urllib.error.URLError, OSError) as e:
            from app.handler.exceptions import RemoteApiError
            raise RemoteApiError("connection_failed", f"Gemini: {e}")

        if abort_hook is not None:
            abort_hook(resp)

        # Synthetic message id — Gemini has no equivalent of OpenAI's chunk.id
        msg_id = f"gemini-{uuid.uuid4().hex[:8]}"
        # tool_call_index advances per functionCall part so multiple tool calls
        # in the same stream get distinct indices (matching OpenAI's model).
        tool_call_index = 0
        # Map index → synthetic id (first chunk for each call carries an id;
        # subsequent argument-fragment chunks reference the same index).
        tool_call_ids: dict[int, str] = {}
        accumulated_usage: dict | None = None

        try:
            for raw_line in resp:
                line = raw_line.decode("utf-8", errors="replace").strip()
                if not line or not line.startswith("data:"):
                    continue
                data = line[len("data:"):].strip()
                try:
                    chunk = json.loads(data)
                except json.JSONDecodeError:
                    logger.warning(
                        "chat_completions_stream: malformed Gemini SSE chunk: %r",
                        data[:120],
                    )
                    continue

                # Capture usage metadata (emitted on the final chunk by Gemini)
                if "usageMetadata" in chunk:
                    meta = chunk["usageMetadata"]
                    accumulated_usage = {
                        "prompt_tokens": meta.get("promptTokenCount", 0),
                        "completion_tokens": meta.get("candidatesTokenCount", 0),
                        "total_tokens": meta.get("totalTokenCount", 0),
                    }

                for candidate in chunk.get("candidates", []):
                    parts = candidate.get("content", {}).get("parts", [])
                    for part in parts:
                        if "text" in part:
                            yield {
                                "id": msg_id,
                                "choices": [{"delta": {"content": part["text"]}}],
                            }
                        elif "functionCall" in part:
                            fc = part["functionCall"]
                            if tool_call_index not in tool_call_ids:
                                tool_call_ids[tool_call_index] = (
                                    f"gemini-tc-{uuid.uuid4().hex[:8]}"
                                )
                            tc_id = tool_call_ids[tool_call_index]
                            # Gemini delivers the full args dict in one part, so
                            # we serialise it once as a complete JSON string — the
                            # OpenAI-compat parser accumulates args_delta strings.
                            args_json = json.dumps(fc.get("args") or {})
                            yield {
                                "id": msg_id,
                                "choices": [{"delta": {"tool_calls": [{
                                    "index": tool_call_index,
                                    "id": tc_id,
                                    "function": {
                                        "name": fc.get("name", ""),
                                        "arguments": args_json,
                                    },
                                }]}}],
                            }
                            tool_call_index += 1

            # Emit final usage chunk so RemoteChatSession.stream() can capture it
            if accumulated_usage is not None:
                yield {"choices": [], "usage": accumulated_usage}
        finally:
            if resp is not None:
                try:
                    resp.close()
                except Exception:
                    pass

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
        if status == 405:
            return RemoteApiError("endpoint_invalid", body[:200])
        return RemoteApiError("remote_error", f"Gemini {status}: {body[:200]}")

    @staticmethod
    def _methods_to_capabilities(model_id: str, methods: list[str]) -> list[str]:
        """
        Infer capabilities from supportedGenerationMethods.

        Common methods:
        - generateContent -> text (+ tools — every generateContent model on the
          Gemini API supports `tools=[{functionDeclarations}]`, Wave 4.6 wired
          the converter)
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

        # Tool calling — `generateContent` always accepts a `tools=[...]` array.
        # Without this tag the agent picker (filters by capabilities.tools)
        # never shows Gemini models even though Wave 4.6 already supports them.
        if "generateContent" in methods:
            caps.append("tools")

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
