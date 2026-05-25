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
from typing import Callable, Optional

from .base import RemoteProvider, RemoteModel

logger = logging.getLogger(__name__)

DEFAULT_OLLAMA_ENDPOINT = "http://localhost:11434"


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

    def connect(self) -> bool:
        """Check if the Ollama service is running."""
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
        """List installed Ollama models (with capability detection)."""
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

        # Fallback: infer from name and families
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
            resp = urllib.request.urlopen(req, timeout=30)
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
