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


class AgentError(Exception):
    """Typed error for agent service; .code is an i18n key."""
    def __init__(self, code: str, message: str = ""):
        self.code = code
        self.message = message
        super().__init__(message or code)


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

            # Normalise messages: ag-ui SDK may pass Pydantic model objects
            # (UserMessage / SystemMessage / etc.) or plain dicts.  Downstream
            # session.stream() (LocalChatSession / RemoteChatSession) expects
            # plain dicts with at least {"role": ..., "content": ...}.
            def _msg_to_dict(m) -> dict:
                if isinstance(m, dict):
                    return m
                # Pydantic model: use model_dump() then drop None values that
                # llama-server / remote APIs don't understand (name, encrypted_value…)
                d = m.model_dump(exclude_none=True, by_alias=False)
                return d

            messages: list[dict] = [_msg_to_dict(m) for m in input.messages]

            # Prepend system prompt (M22) if no system message in input
            if not any(m.get("role") == "system" for m in messages):
                messages.insert(0, {
                    "role": "system",
                    "content": AGENT_SYSTEM_PROMPT,
                })

            # Normalise tools: ag-ui Tool objects → plain dicts
            def _tool_to_dict(t) -> dict:
                if isinstance(t, dict):
                    return t
                return t.model_dump(exclude_none=True, by_alias=False)

            tools: list[dict] = [_tool_to_dict(t) for t in (input.tools or [])]

            with self._chat.session(**session_kwargs) as session:
                async for chunk in session.stream(
                    messages=messages, tools=tools,
                    max_tokens=4096, temperature=0.1,
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
                session.kill_process()
            raise
        except AgentError as e:
            yield encoder.encode(RunErrorEvent(code=e.code, message=e.message))
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

        Local: "qwen3:8b"           → {model_family:'qwen3', model_size:'8b'}
               "qwen3vl:8b:Q4_K_M"  → {model_family:'qwen3vl', model_size:'8b',
                                        quantization:'Q4_K_M'}
        Remote: "remote:openai:3:gpt-4o-mini" →
                {remote_provider:<RemoteProvider>, remote_model:'gpt-4o-mini'}
        """
        if choice.startswith("remote:"):
            parts = choice.split(":")
            if len(parts) < 4:
                raise AgentError("agent.error.no_model")
            provider_name, conn_id_str, model_id = parts[1], parts[2], ":".join(parts[3:])
            try:
                conn_id = int(conn_id_str)
            except ValueError:
                raise AgentError("agent.error.no_model")
            prov = self._remote.get_provider_for_connection(conn_id, provider_name)
            if prov is None:
                raise AgentError("agent.error.model_unavailable")
            return {"remote_provider": prov, "remote_model": model_id}

        # Local "family:size[:quant]"
        if ":" not in choice:
            raise AgentError("agent.error.no_model")
        family, rest = choice.split(":", 1)
        if ":" in rest:
            size, quant = rest.split(":", 1)
            return {"model_family": family, "model_size": size,
                    "quantization": quant}
        return {"model_family": family, "model_size": rest}
