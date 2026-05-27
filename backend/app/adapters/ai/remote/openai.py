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
from typing import Callable, Iterator, Optional

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


# ═══════════════════════════════════════════════════════════
# Strict-mode tool calling adapter (Structured Outputs)
# ═══════════════════════════════════════════════════════════
# Why: gpt-4o-mini reliably emits `arguments: "{}"` for tools with required
# fields unless strict mode is enabled.  Strict mode runs constrained decoding
# on the tool_calls path, eliminating that failure (bug #15).
#
# Spec: core/.claude/specs/2026-05-27-openai-strict-tool-calling-design.md

# Primitive union for "any value" slots (set_field.value).
# OpenAI strict mode does NOT support multi-element type arrays like
# `["string","number","boolean","null"]`; it requires either single-type
# or `anyOf` for branching.
_STRICT_PRIMITIVE_ANYOF: dict = {
    "anyOf": [
        {"type": "string"},
        {"type": "number"},
        {"type": "boolean"},
        {"type": "null"},
    ],
}


def _strictify_schema(schema: dict) -> dict:
    """Convert a permissive tool parameter schema into one that satisfies
    OpenAI Structured Outputs strict mode constraints.

    See spec §3.2 for full design; this docstring summarizes:
    - Root must be {type:"object", properties:{...}}; raises ValueError otherwise
    - Adds `additionalProperties: false`
    - Overwrites `required` to list every key in properties
    - Replaces empty {} value-slot with `_STRICT_PRIMITIVE_ANYOF`
    - Raises ValueError on nested object / array-of-object / anyOf/oneOf/
      allOf/$ref/$defs in property (unsupported; fail loudly)
    - Idempotent: applying twice yields the same result
    """
    if not isinstance(schema, dict):
        raise ValueError(
            f"_strictify_schema: root must be a dict, got {type(schema).__name__}"
        )

    s = dict(schema)

    if s.get("type") != "object":
        raise ValueError(
            f"_strictify_schema: root schema must declare type:'object' (got {s.get('type')!r}); "
            f"zero-arg tool should use {{type:'object', properties:{{}}}}"
        )

    props = s.get("properties") or {}
    new_props: dict = {}
    for k, v in props.items():
        if not isinstance(v, dict):
            raise ValueError(
                f"_strictify_schema: property {k!r} is not a dict schema "
                f"(got {type(v).__name__})"
            )
        # Empty {} = "any" — replace with primitive anyOf.
        if not v:
            new_props[k] = dict(_STRICT_PRIMITIVE_ANYOF)
            continue
        # Idempotency: a property already holding our own primitive-union
        # anyOf shape passes through unchanged.  Without this, the anyOf
        # branch-rejection below would refuse a schema we ourselves emit.
        if v == _STRICT_PRIMITIVE_ANYOF:
            new_props[k] = v
            continue
        # Reject shapes we don't recurse into so future tool authors
        # see the limit explicitly instead of getting a runtime 400 from OpenAI.
        if v.get("type") == "object":
            raise ValueError(
                f"_strictify_schema: nested object in property {k!r} not supported; "
                f"flatten the schema or extend the adapter"
            )
        if v.get("type") == "array":
            items = v.get("items")
            if isinstance(items, dict) and items.get("type") == "object":
                raise ValueError(
                    f"_strictify_schema: array-of-object in property {k!r} not supported"
                )
        for branch_key in ("anyOf", "oneOf", "allOf", "$ref", "$defs"):
            if branch_key in v:
                raise ValueError(
                    f"_strictify_schema: {branch_key!r} in property {k!r} not supported "
                    f"(only the self-inserted primitive-union anyOf is allowed)"
                )
        new_props[k] = v

    s["properties"] = new_props
    s["required"] = list(new_props.keys())
    s["additionalProperties"] = False
    return s


def _to_openai_strict_tools(flat_tools: list[dict]) -> list[dict]:
    """Wrap AG-UI flat tool defs into OpenAI strict function shape.

    AG-UI flat shape:     {name, description, parameters}
    OpenAI strict shape:  {type:"function", function:{...strict schema..., strict:true}}

    Agent path only sends flat tools (RemoteChatSession.stream → frontend
    AG-UI TOOLS); accepting caller-built nested shapes would risk silently
    shipping non-strict tools.  We therefore only accept flat shape and
    raise on anything else to fail loudly.
    """
    wire: list[dict] = []
    for t in flat_tools:
        if "type" in t or "function" in t:
            raise ValueError(
                "_to_openai_strict_tools: nested OpenAI shape not accepted; "
                "agent path must send AG-UI flat shape {name, description, parameters}"
            )
        if "name" not in t:
            raise ValueError("_to_openai_strict_tools: tool missing 'name'")
        if "description" not in t:
            raise ValueError(f"_to_openai_strict_tools: tool {t['name']!r} missing 'description'")
        if "parameters" not in t:
            raise ValueError(f"_to_openai_strict_tools: tool {t['name']!r} missing 'parameters'")
        wire.append({
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t["description"],
                "parameters": _strictify_schema(t["parameters"]),
                "strict": True,
            },
        })
    return wire


# Minimum max_output_tokens for o-series Responses API calls with reasoning.
# Even at effort="low", o4-mini consumes ~64-100 reasoning tokens before producing
# any visible output. A budget below this yields an empty response (production bug
# 2026-05). The frame_select task only needs a single digit as output, so 200 is
# a conservative ceiling that always succeeds while adding negligible latency.
_REASONING_MIN_TOKENS = 200


class OpenAIProvider(RemoteProvider):
    """
    OpenAI REST API Provider

    Supports:
    - Connection check (GET /v1/models)
    - Model listing (GET /v1/models)
    - Text chat (POST /v1/chat/completions)
    """

    PROVIDER_NAME = "openai"
    IMAGE_PREP_MODE = "recompress"

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

    def get_summary_chunking_hints(self, model: str) -> dict:
        """Most current OpenAI text models have >=128k context (gpt-4o-mini,
        gpt-4o, o4-mini, gpt-5 family). Use 128k / 24k as the conservative
        default — older models (gpt-3.5-turbo at 16k) would have a chunk
        truncated server-side, which is a graceful degradation.

        Per-model tier lookup is out of scope; the OpenAI API doesn't expose
        a stable context-window field on /v1/models.
        """
        return {"n_ctx": 128000, "model_cap": 24000}

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
        """OpenAI chat — 4-path dispatcher:
        abort_hook=None + non-Responses → _chat_completions (blocking)
        abort_hook=None + Responses     → _chat_responses (blocking)
        abort_hook set  + non-Responses → _chat_completions_streaming
        abort_hook set  + Responses     → _chat_responses_streaming

        task: forwarded to Responses paths to set reasoning.effort="low".
        Chat Completions paths accept it but ignore it (no thinking on
        gpt-4o / gpt-3.5 series).
        """
        if abort_hook is None:
            if self._needs_responses_api(model):
                return self._chat_responses(model, messages, max_tokens, task=task)
            return self._chat_completions(model, messages, max_tokens, temperature)
        if self._needs_responses_api(model):
            return self._chat_responses_streaming(
                model, messages, max_tokens, abort_hook, task=task,
            )
        return self._chat_completions_streaming(
            model, messages, max_tokens, temperature, abort_hook,
        )

    def _chat_completions(self, model: str, messages: list[dict], max_tokens: int, temperature: float, *, task: Optional[str] = None) -> str:
        """POST /v1/chat/completions (blocking). task kwarg accepted but ignored — no thinking on these models."""
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

    def _chat_completions_streaming(
        self, model: str, messages: list[dict],
        max_tokens: int, temperature: float,
        abort_hook: Callable,
        *,
        task: Optional[str] = None,
    ) -> str:
        """POST /v1/chat/completions with stream:true (SSE). task kwarg accepted but ignored — no thinking on these models."""
        token_key = "max_completion_tokens" if self._is_new_model(model) else "max_tokens"
        payload = {
            "model": model,
            "messages": messages,
            token_key: max_tokens,
            "temperature": temperature,
            "stream": True,
        }
        body = json.dumps(payload).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        req = urllib.request.Request(
            f"{self.endpoint}/v1/chat/completions",
            data=body, headers=headers, method="POST",
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
                if payload_s == "[DONE]":
                    break
                try:
                    obj = json.loads(payload_s)
                except json.JSONDecodeError:
                    continue
                choices = obj.get("choices", [])
                if not choices:
                    continue
                delta = choices[0].get("delta", {}).get("content", "")
                if delta:
                    parts.append(delta)
            return "".join(parts).strip()
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            raise self._parse_error(e.code, body)
        except urllib.error.URLError as e:
            raise RemoteApiError("connection_failed", f"OpenAI: {e}")
        except OSError as e:
            raise RemoteApiError("connection_failed", f"OpenAI: {e}")
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
        """Synchronous generator yielding raw OpenAI Chat Completions SSE chunks.

        Yields raw chunk dicts (same shape as LlamaServer.chat_stream).
        Caller parses delta/tool_calls via _parse_openai_compat_chunk
        (chat_service.py).  Used by RemoteChatSession.stream() for the agent
        tool-calling path.

        Args:
            tools: Tool list forwarded as-is; omitted (empty list) when None.
            abort_hook: Invoked exactly once immediately after urlopen returns.
                Lets RemoteChatSession stash the response for cross-thread close.
        """
        # Chat Completions does not support reasoning models — callers should
        # call chat() directly for o-series / gpt-5 (which routes to Responses).
        token_key = "max_completion_tokens" if self._is_new_model(model) else "max_tokens"
        # Same wire-format wrapping as LlamaServer.chat_stream: AG-UI passes a
        # flat `{name, description, parameters}` tool shape; OpenAI requires
        # the nested `{type: "function", function: {...}}` envelope.  Wrap any
        # flat entry on the way out; pass already-nested tools through so
        # callers that built the OpenAI shape directly still work.
        wire_tools: list[dict] = []
        for t in tools or []:
            if "type" in t and "function" in t:
                wire_tools.append(t)
            else:
                wire_tools.append({"type": "function", "function": t})
        payload: dict = {
            "model": model,
            "messages": messages,
            "tools": wire_tools,
            "tool_choice": "auto" if wire_tools else "none",
            token_key: max_tokens,
            "temperature": temperature,
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        body = json.dumps(payload).encode("utf-8")
        headers: dict = {
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        req = urllib.request.Request(
            f"{self.endpoint}/v1/chat/completions",
            data=body, headers=headers, method="POST",
        )

        from app.handler.exceptions import RemoteApiError

        resp = None
        try:
            # 180s socket timeout: cancel arrives via abort_hook → resp.close()
            # from another thread, not timeout.
            resp = urllib.request.urlopen(req, timeout=180)
        except urllib.error.HTTPError as e:
            body_err = e.read().decode("utf-8", errors="replace")[:200]
            raise self._parse_error(e.code, body_err)
        except (urllib.error.URLError, OSError) as e:
            raise RemoteApiError("connection_failed", f"OpenAI: {e}")

        if abort_hook is not None:
            abort_hook(resp)

        try:
            for raw_line in resp:
                line = raw_line.decode("utf-8", errors="replace").strip()
                if not line or not line.startswith("data:"):
                    continue
                data = line[len("data:"):].strip()
                if data == "[DONE]":
                    return
                try:
                    yield json.loads(data)
                except json.JSONDecodeError:
                    logger.warning("chat_completions_stream: malformed SSE chunk: %r", data[:120])
        finally:
            if resp is not None:
                try:
                    resp.close()
                except Exception:
                    pass

    def chat_responses_stream(
        self,
        *,
        model: str,
        messages: list[dict],
        tools: list[dict] | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.1,
        abort_hook: Optional[Callable] = None,
    ) -> Iterator[dict]:
        """OpenAI Responses API streaming with tool calling.

        Not implemented in Phase 1 (Wave 4 Task 4.5).  Responses-API tool
        calling uses different event types (response.function_call.delta, etc.)
        that require a dedicated parser.  Use a Chat Completions model
        (gpt-4o, gpt-4o-mini) for the agent in Phase 1.
        """
        raise NotImplementedError(
            "OpenAI Responses streaming + tool calling deferred to follow-up; "
            "use a chat-completions model (gpt-4o, gpt-4o-mini) for agent in Phase 1."
        )

    def _convert_to_responses_input(self, messages: list[dict]) -> list[dict]:
        """Convert Chat Completions message shape to Responses API input shape.

        text → input_text, image_url → input_image. Used by both blocking
        _chat_responses and streaming _chat_responses_streaming.
        """
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
        return converted

    def _chat_responses(self, model: str, messages: list[dict], max_tokens: int, *, task: Optional[str] = None) -> str:
        """POST /v1/responses (blocking).

        When task="frame_select", sets reasoning.effort="low" and bumps
        max_output_tokens to _REASONING_MIN_TOKENS if needed. Even at
        effort="low", o4-mini consumes ~64-100 reasoning tokens before any
        visible output — a budget below _REASONING_MIN_TOKENS yields empty
        responses (production bug, 2026-05).
        """
        effective_tokens = max_tokens
        if task == "frame_select":
            effective_tokens = max(max_tokens, _REASONING_MIN_TOKENS)
        payload = {
            "model": model,
            "input": self._convert_to_responses_input(messages),
            "max_output_tokens": effective_tokens,
        }
        if task == "frame_select":
            # "low" is the minimum effort level accepted by the Responses API
            # (valid values: "low" | "medium" | "high"; "minimal" is not a valid value).
            payload["reasoning"] = {"effort": "low"}
        try:
            with self._make_request("/v1/responses", method="POST",
                                    data=payload, timeout=600) as resp:
                result = json.loads(resp.read())
                output = result.get("output", [])
                for item in output:
                    if item.get("type") == "message":
                        for content in item.get("content", []):
                            if content.get("type") == "output_text":
                                return content.get("text", "").strip()
                return result.get("output_text", "").strip()
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            raise self._parse_error(e.code, body)
        except (urllib.error.URLError, OSError) as e:
            from app.handler.exceptions import RemoteApiError
            raise RemoteApiError("connection_failed", f"OpenAI: {e}")

    def _chat_responses_streaming(
        self, model: str, messages: list[dict],
        max_tokens: int, abort_hook: Callable,
        *,
        task: Optional[str] = None,
    ) -> str:
        """POST /v1/responses with stream:true (SSE event:/data: pairs).

        When task="frame_select", sets reasoning.effort="low" and bumps
        max_output_tokens to _REASONING_MIN_TOKENS if needed (same as
        blocking path — see _chat_responses docstring).
        """
        effective_tokens = max_tokens
        if task == "frame_select":
            effective_tokens = max(max_tokens, _REASONING_MIN_TOKENS)
        payload = {
            "model": model,
            "input": self._convert_to_responses_input(messages),
            "max_output_tokens": effective_tokens,
            "stream": True,
        }
        if task == "frame_select":
            # "low" is the minimum effort level accepted by the Responses API
            # (valid values: "low" | "medium" | "high"; "minimal" is not a valid value).
            payload["reasoning"] = {"effort": "low"}
        body = json.dumps(payload).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
            "Authorization": f"Bearer {self.api_key}",
        }
        req = urllib.request.Request(
            f"{self.endpoint}/v1/responses",
            data=body, headers=headers, method="POST",
        )

        from app.handler.exceptions import RemoteApiError
        resp = None
        try:
            # 180s socket timeout: cloud TTFT on large summarize chunks (~9k+
            # tokens with thinking) routinely exceeds 30s; cancel still works
            # via abort_hook → resp.close() from another thread, not timeout.
            resp = urllib.request.urlopen(req, timeout=180)
            abort_hook(resp)

            current_event: Optional[str] = None
            parts: list[str] = []
            refusal_parts: list[str] = []
            for raw in resp:
                line = raw.rstrip(b"\r\n")
                if not line:
                    current_event = None
                    continue
                if line.startswith(b"event: "):
                    current_event = line[7:].decode("ascii", errors="replace").strip()
                    continue
                if not line.startswith(b"data: "):
                    continue
                payload_s = line[6:].decode("utf-8", errors="replace").strip()
                if not payload_s:
                    continue

                if current_event == "response.output_text.delta":
                    try: obj = json.loads(payload_s)
                    except json.JSONDecodeError: continue
                    d = obj.get("delta", "")
                    if d: parts.append(d)
                elif current_event == "response.refusal.delta":
                    try: obj = json.loads(payload_s)
                    except json.JSONDecodeError: continue
                    d = obj.get("delta", "")
                    if d: refusal_parts.append(d)
                elif current_event == "response.completed":
                    break
                elif current_event == "response.failed":
                    try:
                        obj = json.loads(payload_s)
                        msg = obj.get("response", {}).get("error", {}).get(
                            "message", payload_s
                        )
                    except (json.JSONDecodeError, AttributeError):
                        msg = payload_s
                    raise RemoteApiError(
                        "remote_error", f"OpenAI Responses failed: {msg[:200]}"
                    )
                elif current_event == "error":
                    # ResponseErrorEvent — literal "error" (no "response." prefix),
                    # per OpenAI SDK src/openai/types/responses/response_error_event.py
                    try:
                        obj = json.loads(payload_s)
                        msg = obj.get("message", payload_s)
                    except json.JSONDecodeError:
                        msg = payload_s
                    raise RemoteApiError(
                        "remote_error", f"OpenAI Responses error: {msg[:200]}"
                    )
                # 其他 event 一律忽略
            if refusal_parts:
                raise RemoteApiError(
                    "refused",
                    f"OpenAI Responses refused: {''.join(refusal_parts)[:200]}",
                )
            return "".join(parts).strip()
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            raise self._parse_error(e.code, body)
        except urllib.error.URLError as e:
            raise RemoteApiError("connection_failed", f"OpenAI: {e}")
        except OSError as e:
            raise RemoteApiError("connection_failed", f"OpenAI: {e}")
        finally:
            if resp is not None:
                try: resp.close()
                except Exception: pass

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
