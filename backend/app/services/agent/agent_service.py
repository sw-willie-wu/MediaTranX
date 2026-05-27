"""AgentService — single LLM-round orchestrator for the Agent Chat Bubble.

Stateless across rounds: each call to run() opens a fresh ChatService.session()
context and streams tool/text chunks through the ag-ui-protocol wire format.

Cancel handling: this generator owns the cancel hook (spec §9 step 6).
On CancelledError the except block invokes session.kill_process() explicitly —
chat_service.stream() runs in cancel_guard pass-through mode (does NOT poll on
its own).
"""
from __future__ import annotations
import asyncio
import logging
from typing import AsyncIterator

from app.services.agent._ag_ui_compat import (
    RunAgentInput, RunStartedEvent, RunFinishedEvent, RunErrorEvent,
    TextMessageChunkEvent, ToolCallChunkEvent,
    make_encoder, emit_run_finished_with_usage,
)
from app.services.agent._system_prompt import AGENT_SYSTEM_PROMPT

logger = logging.getLogger(__name__)

# Agent inference constants.
# NOTE: Agent path intentionally bypasses get_inference_config() because tool
# calling requires specific sampling settings for reliable JSON grammar output.
# Qwen3 / Gemma4 tool tests (SPIKE-B/D) confirmed 0.1 / 4096 as stable floor.
AGENT_DEFAULT_TEMPERATURE = 0.1
AGENT_DEFAULT_MAX_TOKENS = 4096


class AgentError(Exception):
    """Typed error for agent service; .code is an i18n key."""
    def __init__(self, code: str, message: str = ""):
        self.code = code
        self.message = message
        super().__init__(message or code)


def _msg_to_dict(m) -> dict:
    """Normalise a message to a plain dict for session.stream().

    ag-ui SDK may pass Pydantic model objects (UserMessage / SystemMessage /
    etc.) or plain dicts.  Downstream session.stream() expects plain dicts
    with at least {"role": ..., "content": ...}.

    Strips any SDK-internal "id" field to avoid sending unknown keys to
    llama-server or remote APIs.  Also strips empty `tool_calls` (or
    camelCase `toolCalls`) on assistant messages — OpenAI returns 400
    `Invalid 'messages[N].tool_calls': empty array` if the key is present
    with `[]` (must be omitted entirely or have ≥1 entry).
    """
    if isinstance(m, dict):
        d = {k: v for k, v in m.items() if k != "id"}
    else:
        # Pydantic model: use model_dump() then drop None values and the
        # SDK-internal "id" that llama-server / remote APIs don't understand.
        d = m.model_dump(exclude_none=True, by_alias=False)
        d.pop("id", None)
    if d.get("role") == "assistant":
        if not d.get("tool_calls"):
            d.pop("tool_calls", None)
        if not d.get("toolCalls"):
            d.pop("toolCalls", None)
    return d


def _tool_to_dict(t) -> dict:
    """Normalise a Tool to a plain dict for session.stream()."""
    if isinstance(t, dict):
        return t
    return t.model_dump(exclude_none=True, by_alias=False)


class AgentService:
    """Single LLM-round orchestrator. Stateless across rounds.

    Cancel handling: this generator owns the cancel hook (spec §9 step 6).
    On CancelledError the except block invokes session.kill_process()
    explicitly — chat_service.stream() runs in cancel_guard pass-through
    mode (does NOT poll on its own).
    """

    def __init__(self, chat_service, remote_service):
        self._chat = chat_service
        self._remote = remote_service

    async def run(self, input: RunAgentInput,
                  accept: str | None = None) -> AsyncIterator[str]:
        encoder = make_encoder(accept)
        # SPIKE-A finding: both run_id and thread_id required
        yield encoder.encode(RunStartedEvent(
            run_id=input.run_id, thread_id=input.thread_id))

        session = None
        usage: dict | None = None
        try:
            choice = (input.state or {}).get("agent_model_choice")
            if not choice:
                raise AgentError("agent.error.no_model")

            session_kwargs = self._resolve_model_choice(choice)

            messages: list[dict] = [_msg_to_dict(m) for m in input.messages]

            # Guard: frontend always pushes a user message before calling run(),
            # but defend against empty list to avoid a silent system-only request.
            if not messages:
                raise AgentError("agent.error.internal", "empty messages list")

            # Prepend system prompt (M22) if no system message in input
            if not any(m.get("role") == "system" for m in messages):
                messages.insert(0, {
                    "role": "system",
                    "content": AGENT_SYSTEM_PROMPT,
                })

            tools: list[dict] = [_tool_to_dict(t) for t in (input.tools or [])]

            with self._chat.session(**session_kwargs) as session:
                async for chunk in session.stream(
                    messages=messages, tools=tools,
                    max_tokens=AGENT_DEFAULT_MAX_TOKENS,
                    temperature=AGENT_DEFAULT_TEMPERATURE,
                ):
                    if chunk["type"] == "delta":
                        yield encoder.encode(TextMessageChunkEvent(
                            message_id=chunk["message_id"],
                            role="assistant",
                            delta=chunk["text"],
                        ))
                    elif chunk["type"] == "tool_call":
                        yield encoder.encode(ToolCallChunkEvent(
                            tool_call_id=chunk["id"],
                            tool_call_name=chunk["name"],
                            parent_message_id=chunk["parent_message_id"],
                            delta=chunk["args_delta"],
                        ))
                    elif chunk["type"] == "done":
                        usage = chunk.get("usage")
                        break
        except asyncio.CancelledError:
            if session is not None:
                # Intentional belt-and-braces: LocalChatSession.stream()'s finally
                # ALSO calls kill_process() on consumer abandon (Task 1.3 fix-of-fix).
                # Idempotent. Removing either is a leak — both are needed because
                # cancel paths differ for direct CancelledError vs await q.get() abort.
                session.kill_process()
            raise
        except AgentError as e:
            yield encoder.encode(RunErrorEvent(code=e.code, message=e.message))
        except NotImplementedError as e:
            # Provider does not yet support streaming tool calling
            # (Gemini — Wave 4.6 deliverable; Ollama done in Wave 4.7).
            yield encoder.encode(RunErrorEvent(
                code="agent.error.tools_not_supported",
                message=str(e),
            ))
        except Exception as e:
            logger.exception("Agent run failed")
            yield encoder.encode(RunErrorEvent(
                code="agent.error.internal", message=str(e)))
        finally:
            # SPIKE-A: thread_id is required on RunFinishedEvent
            yield emit_run_finished_with_usage(
                encoder, run_id=input.run_id, thread_id=input.thread_id,
                usage=usage)

    def _resolve_model_choice(self, choice: str) -> dict:
        """Mirror frontend parseModelValue (useModelOptions.ts:84).

        Local:  "qwen3:8b"               → {model_family, model_size}
                "qwen3vl:8b:Q4_K_M"      → {model_family, model_size, quantization}
        Remote: "remote:<provider>:<conn_id>:<model_id>"
                "remote:<provider>:<conn_id>:<model_id_with:colons>"
                → {remote_provider, remote_model}

        Remote routing (Wave 4 Tasks 4.5 / 4.7):
        - OpenAI (Task 4.5) and Ollama (Task 4.7) providers that expose
          chat_completions_stream() are fully supported.
        - Gemini streaming tool-calling is deferred (Wave 4.6);
          RemoteChatSession.stream() will raise NotImplementedError for Gemini,
          which AgentService.run() catches as agent.error.tools_not_supported.
        """
        if choice.startswith("remote:"):
            # "remote:<provider>:<conn_id>:<model_id>" — model_id may itself
            # contain colons (e.g. "qwen3:8b-instruct" for Ollama).
            parts = choice.split(":", 3)   # ["remote", provider, conn_id, model_id]
            if len(parts) < 4:
                raise AgentError("agent.error.no_model")
            _, provider, conn_id_str, model_id = parts
            if not provider or not conn_id_str or not model_id:
                raise AgentError("agent.error.no_model")
            try:
                conn_id = int(conn_id_str)
            except ValueError:
                raise AgentError("agent.error.no_model")
            prov = self._remote.get_provider_for_connection(conn_id, provider)
            if prov is None:
                raise AgentError(
                    "agent.error.model_unavailable",
                    f"No active connection found for provider '{provider}' (conn_id={conn_id}).",
                )
            return {"remote_provider": prov, "remote_model": model_id}

        # Local "family:size[:quant]"
        if ":" not in choice:
            raise AgentError("agent.error.no_model")
        family, rest = choice.split(":", 1)
        if not family or not rest:
            raise AgentError("agent.error.no_model")
        if ":" in rest:
            size, quant = rest.split(":", 1)
            if not size:
                raise AgentError("agent.error.no_model")
            return {"model_family": family, "model_size": size,
                    "quantization": quant}
        return {"model_family": family, "model_size": rest}
