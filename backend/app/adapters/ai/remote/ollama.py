"""
Ollama Provider
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Access local or remote Ollama services via REST API.
API docs: https://github.com/ollama/ollama/blob/main/docs/api.md
"""
from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from typing import Callable, Iterator, Optional

from .base import RemoteProvider, RemoteModel, PROBE_TIMEOUT

logger = logging.getLogger(__name__)

DEFAULT_OLLAMA_ENDPOINT = "http://localhost:11434"

# num_ctx bounds for the `options.num_ctx` we send to Ollama in every chat
# request. Background: Ollama's own default when modelfile doesn't set
# PARAMETER num_ctx is 2048-4096; requests that need more get silently
# truncated. So we must send something. But going TOO high (e.g. auto-
# bumping to 16k+ on a 120B model) pushes Ollama to reload-up with a bigger
# KV cache, which can OOM the server — particularly on a shared DGX with
# multiple concurrent loaded models (e.g. one 120B LLM + one 120B-class VLM
# each reserving 20-30GB of KV cache @ 16k can exceed 80GB-per-card limits).
#
# Trade-off picked: cap at 8192 by default — matches the chunking-hints
# fallback used in summary_service so input_budget never asks for more than
# we ourselves announced. Users on bigger DGX with budget for larger KV
# cache can override via env: `MTX_OLLAMA_MAX_NUM_CTX=32768`.
import os as _os
_NUM_CTX_FLOOR = 4096
_NUM_CTX_CAP = int(_os.environ.get("MTX_OLLAMA_MAX_NUM_CTX", "8192"))


def _estimate_messages_tokens(messages: list[dict]) -> int:
    """Rough token estimate: total char count / 3. Conservative for mixed
    English/Chinese transcript content; only used to size num_ctx (over-
    estimating is harmless, under-estimating causes silent truncation)."""
    total_chars = 0
    for msg in messages:
        c = msg.get("content", "")
        if isinstance(c, str):
            total_chars += len(c)
        elif isinstance(c, list):
            for part in c:
                if isinstance(part, dict):
                    total_chars += len(part.get("text", "") or "")
    return total_chars // 3


def _format_proxy_error(obj: dict) -> str:
    """Combine `error` (short proxy status code) with `detail` (upstream body)
    when both present, so diagnostic info isn't lost.

    LiteLLM-style proxies wrap upstream failures as:
        {"done_reason":"error", "error":"backend returned 500",
         "detail":"... upstream model errored: tokens exceed ctx ..."}
    Earlier `obj.get("error") or obj.get("detail")` swallowed `detail` because
    `error` is a truthy short string — making proxy 500s impossible to debug
    from logs alone. Truncated to keep log lines reasonable.
    """
    parts = [str(x) for x in (obj.get("error"), obj.get("detail")) if x]
    return ": ".join(parts)[:300] if parts else str(obj)[:300]


def _count_images(messages: list[dict]) -> int:
    """Count image attachments across both shapes we send to Ollama proxies.

    - Ollama-native:    {"content": "...", "images": [b64, b64, ...]}
    - OpenAI-compat:    {"content": [{"type":"image_url", ...}, ...]}

    Defensive on both — LiteLLM-style gateways accept the OpenAI shape and we
    might route summary VLM calls through OllamaProvider regardless.
    """
    n = 0
    for m in messages:
        imgs = m.get("images")
        if isinstance(imgs, list):
            n += len(imgs)
        c = m.get("content")
        if isinstance(c, list):
            for p in c:
                if isinstance(p, dict) and p.get("type") in ("image_url", "image"):
                    n += 1
    return n


def _compute_num_ctx(messages: list[dict], max_tokens: int) -> int:
    """Bound (prompt_estimate + max_tokens + safety) between FLOOR (so we
    don't ever request less than Ollama's typical default) and CAP (so we
    don't trigger reload-up on the server that may OOM a shared DGX).

    Prompts that genuinely need more than CAP will see Ollama truncate
    silently — user should raise MTX_OLLAMA_MAX_NUM_CTX OR use a smaller
    model in that case."""
    needed = _estimate_messages_tokens(messages) + max_tokens + 500  # 500 safety
    return max(_NUM_CTX_FLOOR, min(needed, _NUM_CTX_CAP))


class OllamaProvider(RemoteProvider):
    """
    Ollama REST API Provider

    Supports:
    - Connection check (GET /api/version)
    - Model listing (GET /api/tags)
    - Text chat (POST /api/chat)
    """

    PROVIDER_NAME = "ollama"
    IMAGE_PREP_MODE = "raw"

    def __init__(self, endpoint: str = DEFAULT_OLLAMA_ENDPOINT, api_key: Optional[str] = None):
        super().__init__(endpoint, api_key)
        self._caps_cache: dict[str, list[str]] = {}  # model_name -> capabilities

    def connect(self, timeout: int = PROBE_TIMEOUT) -> bool:
        """Check if the Ollama service is running."""
        try:
            req = urllib.request.Request(
                f"{self.endpoint}/api/version",
                method="GET",
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read())
                version = data.get("version", "unknown")
                logger.info(f"Ollama connected: v{version} at {self.endpoint}")
                return True
        except (urllib.error.URLError, OSError, json.JSONDecodeError) as e:
            logger.warning(f"Ollama connection failed: {e}")
            return False

    def list_models(self, timeout: int = PROBE_TIMEOUT) -> list[RemoteModel]:
        """List installed Ollama models (with capability detection)."""
        try:
            req = urllib.request.Request(
                f"{self.endpoint}/api/tags",
                method="GET",
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
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
        Detect model capabilities.

        Uses the capabilities field from /api/show (native Ollama support).
        Fallback: infer from model name and families.
        """
        # Cache hit
        if model_name in self._caps_cache:
            return self._caps_cache[model_name]

        # Call /api/show to get official capabilities
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
                    # Ollama response format: ["completion", "vision", "tools", "thinking"]
                    # Convert to our format
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

        # Fallback: infer from name and families.
        #
        # Trade-off note: bare substring match on "vl" produces FALSE
        # POSITIVES on names containing "vllm" (vLLM inference engine
        # suffix, e.g. gpt-oss-120b-vllm has no vision). A regex word-
        # bound match removes those — but ALSO removes TRUE POSITIVES
        # where the proxy aliases a real vision model with -vllm suffix
        # (qwen3.5-122b-vllm IS multimodal in user's deployment).
        #
        # Without /api/show capabilities to disambiguate, name-pattern
        # alone can't tell vision-served-via-vllm from text-served-via-
        # vllm. Choose false-positive over false-negative: user can
        # untoggle wrong models in Settings; user can't easily make a
        # silent-text-tagged vision model appear in VLM dropdown.
        # Known-bad text-only models (gpt-oss) should be untoggled in UI.
        caps = ["text"]
        name_lower = model_name.lower()
        if any(kw in name_lower for kw in ["vl", "vision", "llava", "bakllava", "moondream"]):
            caps.append("vision")
        if any(kw in name_lower for kw in ["embed", "nomic-embed", "mxbai-embed"]):
            caps.append("embedding")
        if any(f in families for f in ["clip", "mllama"]):
            if "vision" not in caps:
                caps.append("vision")

        # OQ-7 (template probe fallback): when Ollama's /api/show didn't return
        # a "capabilities" array (older Ollama or proxy), check the chat template
        # for tool-related markers.  Only runs when the primary capabilities path
        # already failed (i.e. we're in the fallback branch).
        if self._supports_tools(model_name):
            caps.append("tools")

        self._caps_cache[model_name] = caps
        return caps

    def _supports_tools(self, model_name: str) -> bool:
        """Probe /api/show template field for tool-call support (OQ-7).

        Returns True only when the Jinja chat template contains tool-related
        variable names ('tools', 'tool_calls', 'function_call',
        'available_tools').  Conservative: falls back to False on any network
        or parse error so we never *over-claim* capabilities.

        Rationale: Ollama 0.4.0+ reports 'tools' in the capabilities array
        (handled by the primary path in _detect_capabilities).  Older Ollama
        versions and LiteLLM-style proxies may not include a capabilities array
        at all; the template is the authoritative source of truth in those cases.
        """
        try:
            payload = json.dumps({"name": model_name}).encode("utf-8")
            req = urllib.request.Request(
                f"{self.endpoint}/api/show",
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read())
            template: str = data.get("template", "") or ""
            template_lower = template.lower()
            return any(marker in template_lower for marker in [
                "tools", "tool_calls", "function_call", "available_tools",
            ])
        except Exception as e:
            logger.debug("Ollama tool template probe failed for %s: %s", model_name, e)
            return False

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
        """Yield raw OpenAI-compat SSE chunks from Ollama /v1/chat/completions.

        Ollama natively speaks the OpenAI Chat Completions wire format via its
        /v1/ sub-path (requires Ollama 0.1.24+).  Chunks are yielded as-is; the
        caller parses delta / tool_calls via _parse_openai_compat_chunk
        (services/llm/chat_service.py).  Used by RemoteChatSession.stream() for
        the agent tool-calling path.

        Ollama-specific notes vs. OpenAI:
        - Endpoint: {endpoint}/v1/chat/completions (same /v1/ prefix as OpenAI).
        - Auth: usually absent for local Ollama; forwarded if api_key is set
          (e.g. for LiteLLM-style proxies that require a token).
        - Tool calling requires Ollama ≥ 0.4.0 AND a model whose chat template
          includes tool-call Jinja variables.  See _supports_tools / OQ-7.
        - The existing chat() method (used by translate / summary / subtitle)
          targets /api/chat (native Ollama NDJSON) and is NOT affected.

        Args:
            tools: Forwarded as-is; empty list sent when None.
            abort_hook: Invoked once immediately after urlopen returns.
                Lets RemoteChatSession stash the response for cross-thread close.
        """
        payload: dict = {
            "model": model,
            "messages": messages,
            "tools": tools or [],
            "tool_choice": "auto" if tools else "none",
            "max_tokens": max_tokens,
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

        resp = None
        try:
            # 180s socket timeout: cancel arrives via abort_hook → resp.close()
            # from another thread, not timeout.  Ollama on a local GPU is fast
            # enough that 180s is never hit in normal operation; same ceiling as
            # OpenAI cloud path for consistency.
            resp = urllib.request.urlopen(req, timeout=180)
        except urllib.error.HTTPError as e:
            body_err = e.read().decode("utf-8", errors="replace")[:200]
            raise RuntimeError(f"ollama API error {e.code}: {body_err}") from e
        except (urllib.error.URLError, OSError) as e:
            raise RuntimeError(f"ollama connection error: {e}") from e

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
                    logger.warning(
                        "chat_completions_stream: malformed Ollama SSE chunk: %r",
                        data[:120],
                    )
        finally:
            if resp is not None:
                try:
                    resp.close()
                except Exception:
                    pass

    def get_model_ctx(self, model_name: str) -> int:
        """Query Ollama for model's context window size via /api/show."""
        try:
            payload = json.dumps({"name": model_name}).encode("utf-8")
            req = urllib.request.Request(
                f"{self.endpoint}/api/show",
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                info = json.loads(resp.read())
                # num_ctx is in model parameters
                params = info.get("parameters", "")
                for line in params.split("\n"):
                    if "num_ctx" in line:
                        parts = line.strip().split()
                        if len(parts) >= 2:
                            return int(parts[-1])
                # Fallback: check modelfile
                modelfile = info.get("modelfile", "")
                for line in modelfile.split("\n"):
                    if "num_ctx" in line.lower():
                        parts = line.strip().split()
                        if len(parts) >= 2:
                            return int(parts[-1])
        except Exception as e:
            logger.warning(f"Failed to query model ctx for {model_name}: {e}")
        return 8192  # Conservative fallback

    def get_summary_chunking_hints(self, model: str) -> dict:
        """Query Ollama /api/show for the model's actual num_ctx.

        Falls back to base default on any network error. model_cap = 75% of
        n_ctx, capped at 16000 (the largest chunk size we've validated for
        coherence; beyond this LLMs start losing track of structural prompts),
        floored at 6000 (parity with the old hardcoded default).
        """
        try:
            n_ctx = self.get_model_ctx(model)
            model_cap = max(6000, min(int(n_ctx * 0.75), 16000))
            return {"n_ctx": n_ctx, "model_cap": model_cap}
        except Exception:
            return super().get_summary_chunking_hints(model)

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
        """Ollama chat completion.

        Dual-path:
        - abort_hook is None → _chat_blocking (legacy single-read,
          timeout=300, stream=False). Used by the 5 existing prov.chat
          callers (subtitle / transcribe / lyrics / doc translate /
          doc ocr); byte-identical behaviour preserved.
        - abort_hook is not None → _chat_streaming (NDJSON line-by-line,
          timeout=30, stream=True, hook receives HTTPResponse so the
          caller can close the socket from another thread to interrupt
          the read). Used by RemoteChatSession for video summary remote.

        task: accepted for interface symmetry; Ollama has no built-in
        thinking budget to suppress, so this kwarg is ignored.

        Spec §F1.
        """
        # Pre-flight log for vision (VLM) calls — the existing telemetry log
        # in summary_service only fires on success, leaving failed VLM picks
        # (e.g. proxy 500) with zero telemetry. frame_picker only reports
        # "VLM pick failed" without model / payload context, so re-running
        # to diagnose is blind. Log model + image count + chosen num_ctx
        # before the HTTP call so failures still leave a paper trail.
        img_count = _count_images(messages)
        if img_count > 0:
            logger.info(
                "Ollama VLM chat: model=%s images=%d num_ctx=%d max_tokens=%d",
                model, img_count,
                _compute_num_ctx(messages, max_tokens), max_tokens,
            )

        if abort_hook is None:
            return self._chat_blocking(model, messages, max_tokens, temperature)
        return self._chat_streaming(model, messages, max_tokens, temperature, abort_hook)

    def _chat_blocking(
        self, model: str, messages: list[dict],
        max_tokens: int, temperature: float,
    ) -> str:
        """Legacy path. Single .read(), stream=False, 300s socket timeout.
        Preserved verbatim for existing callers."""
        payload = {
            "model": model,
            "messages": messages,
            "stream": False,
            "options": {
                "num_predict": max_tokens,
                "temperature": temperature,
                # Tell Ollama how much context this request needs. Without it,
                # Ollama uses modelfile / OLLAMA_CONTEXT_LENGTH default (often
                # 4096) and silently truncates anything bigger. With it,
                # Ollama loads the model with at least num_ctx slots; first
                # request that exceeds the loaded size reloads (slow once,
                # cached after) — NUM_PARALLEL=1 makes this safe.
                "num_ctx": _compute_num_ctx(messages, max_tokens),
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
                # See _chat_streaming for the proxy error-wrapping rationale.
                if result.get("done_reason") == "error" or "error" in result:
                    from app.handler.exceptions import RemoteApiError
                    raise RemoteApiError(
                        "remote_error",
                        f"Ollama proxy error: {_format_proxy_error(result)}",
                    )
                content = result.get("message", {}).get("content", "")
                return content.strip()
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            raise self._parse_error(e.code, body)
        except urllib.error.URLError as e:
            from app.handler.exceptions import RemoteApiError
            raise RemoteApiError("connection_failed", f"Ollama: {e}")
        except OSError as e:
            from app.handler.exceptions import RemoteApiError
            raise RemoteApiError("connection_failed", f"Ollama: {e}")

    def _chat_streaming(
        self, model: str, messages: list[dict],
        max_tokens: int, temperature: float,
        abort_hook: Callable,
    ) -> str:
        """Streamable + cancellable path. stream=True, 30s socket timeout
        per recv; abort_hook(resp) called immediately after urlopen returns
        so the caller can stash for cross-thread close."""
        payload = {
            "model": model,
            "messages": messages,
            "stream": True,
            "options": {
                "num_predict": max_tokens,
                "temperature": temperature,
                # See _chat_blocking comment — num_ctx prevents silent
                # truncation when modelfile / env default is smaller than
                # the request needs.
                "num_ctx": _compute_num_ctx(messages, max_tokens),
            },
        }
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"{self.endpoint}/api/chat",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        from app.handler.exceptions import RemoteApiError
        resp = None
        try:
            # 600s per-recv timeout. Self-hosted big models (gpt-oss-120b,
            # qwen3.5-122b) on LAN proxy show high prefill-TTFT variance —
            # observed chunks ranging 49-117s, with occasional outliers
            # exceeding 180s. Cloud providers (OpenAI/Gemini) stay at 180s
            # since their TTFT is more predictable. Cancel still works via
            # abort_hook -> cross-thread resp.close(), not timeout polling,
            # so a long ceiling doesn't impede user cancel responsiveness.
            resp = urllib.request.urlopen(req, timeout=600)
            # Hook BEFORE entering the read loop — gives the cancel
            # watcher a closable response to act on for the rest of the
            # call. If the hook itself raises (e.g. cancel was pre-queued
            # via RemoteChatSession._kill_pending), the OSError propagates
            # and is wrapped below.
            abort_hook(resp)
            parts: list[str] = []
            for raw in resp:
                line = raw.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                # LiteLLM / OpenAI-compat proxies (e.g. the ttl-test-ollama
                # gateway) wrap upstream failures as a 200 OK NDJSON line:
                #   {"done":true, "done_reason":"error",
                #    "error":"backend returned 400", "detail":"..."}
                # Vanilla Ollama never emits done_reason="error" (it uses
                # "stop"|"length"|"load"|"unload"). Surface it so the LLM
                # chunk loop sees a real exception instead of silent "".
                if obj.get("done_reason") == "error" or "error" in obj:
                    raise RemoteApiError(
                        "remote_error",
                        f"Ollama proxy error: {_format_proxy_error(obj)}",
                    )
                msg = obj.get("message", {})
                if isinstance(msg, dict):
                    delta = msg.get("content", "")
                    if delta:
                        parts.append(delta)
                if obj.get("done") is True:
                    break
            return "".join(parts).strip()
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            raise self._parse_error(e.code, body)
        except urllib.error.URLError as e:
            raise RemoteApiError("connection_failed", f"Ollama: {e}")
        except OSError as e:
            # Includes cross-thread socket-close (cancel-induced) AND real
            # network failures. cancel_guard.finally translates to
            # TaskCancelledError when cancel was signalled. Provider has
            # no visibility into RemoteChatSession._kill_pending, so it
            # ALWAYS raises connection_failed here (spec §F1, MAJOR-C).
            raise RemoteApiError("connection_failed", f"Ollama: {e}")
        finally:
            if resp is not None:
                try:
                    resp.close()
                except Exception:
                    pass

    @staticmethod
    def _parse_error(status: int, body: str):
        """Parse Ollama API error and return a RemoteApiError."""
        from app.handler.exceptions import RemoteApiError
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
        Pull a model (ollama pull).

        Args:
            model_name: Model name (e.g. "llama3.2:3b")
            on_progress: Progress callback (completed_bytes, total_bytes)

        Returns:
            True if successful
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
# Singleton factory
# ═══════════════════════════════════════════════════════════
_ollama: Optional[OllamaProvider] = None


def get_ollama_provider(endpoint: str = DEFAULT_OLLAMA_ENDPOINT) -> OllamaProvider:
    """Get the OllamaProvider singleton."""
    global _ollama
    if _ollama is None or _ollama.endpoint != endpoint:
        _ollama = OllamaProvider(endpoint)
    return _ollama
