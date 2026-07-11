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
import json
import logging
import threading
from typing import AsyncIterator
from uuid import uuid4

from app.services.agent._ag_ui_compat import (
    RunAgentInput, RunStartedEvent, RunFinishedEvent, RunErrorEvent,
    TextMessageChunkEvent, ToolCallChunkEvent,
    make_encoder, emit_run_finished_with_usage,
)
from app.services.agent._system_prompt import pick_system_prompt
from app.services.agent._render_state import render_state

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


_TASK_SUBMITTED_TEXT = "✅ 已送出任務（task_id={task_id}）。可在工作列追蹤進度，完成後再問我。"
_RUN_SUBMITTED_TEXT = "✅ 流程已開始執行（run_id={run_id}）。可在流程頁追蹤各節點進度，完成後再問我。"

# 「執行類」工具:dispatch 成功後不再開 LLM 回合（會踢掉剛提交任務佔用的 GPU）。
_EXECUTE_TOOL_NAMES = {"click_execute", "run_pipeline"}


def _last_tool_result_is_execute_success(messages: list[dict]) -> tuple[str, str] | None:
    """If messages[-1] is a successful execute-class tool result, return
    ("task", task_id) or ("run", run_id); else None. Matches the tool result's
    tool_call_id back to an execute-class tool_call in a preceding assistant
    message, then parses the result content for {ok: true, task_id|run_id}.
    Conservative: ambiguity → None."""
    if not messages:
        return None
    last = messages[-1]
    if last.get("role") != "tool":
        return None
    tcid = last.get("tool_call_id") or last.get("toolCallId")
    if not tcid:
        return None
    is_execute = False
    for m in messages:
        if m.get("role") != "assistant":
            continue
        for tc in (m.get("tool_calls") or m.get("toolCalls") or []):
            if tc.get("id") == tcid and (tc.get("function") or {}).get("name") in _EXECUTE_TOOL_NAMES:
                is_execute = True
                break
        if is_execute:
            break
    if not is_execute:
        return None
    content = last.get("content")
    try:
        data = json.loads(content) if isinstance(content, str) else content
    except (json.JSONDecodeError, TypeError):
        return None
    if isinstance(data, dict) and data.get("ok") is True:
        if data.get("task_id"):
            return ("task", str(data["task_id"]))
        if data.get("run_id"):
            return ("run", str(data["run_id"]))
    return None


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
        errored = False                          # ★ AG-UI conformance: track RUN_ERROR
        is_local = False
        try:
            choice = (input.state or {}).get("agent_model_choice")
            if not choice:
                raise AgentError("agent.error.no_model")

            is_local = bool(choice) and not choice.startswith("remote:")

            session_kwargs = self._resolve_model_choice(choice)

            messages: list[dict] = [_msg_to_dict(m) for m in input.messages]

            # Guard: frontend always pushes a user message before calling run(),
            # but defend against empty list to avoid a silent system-only request.
            if not messages:
                raise AgentError("agent.error.internal", "empty messages list")

            # Prepend system prompt (M22) if no system message in input.
            # Fold the live UI state snapshot (if the frontend supplied one) into
            # the single system message — fresh each request, never persisted to
            # history (it rides input.state, not input.messages).
            if not any(m.get("role") == "system" for m in messages):
                snapshot = (input.state or {}).get("snapshot")
                # 依當輪前端宣告的工具選提示版本（無 create_pipeline → 精簡版；
                # spec: pipeline-feature-gate §3.4）。元素可能是 Pydantic model 或
                # plain dict（比照 _tool_to_dict），取名須 dict-safe；正規化清單在
                # 下方才建立，這裡直接讀原始 input.tools。
                tool_names = {
                    n for t in (input.tools or [])
                    if (n := (getattr(t, "name", None) or (t.get("name") if isinstance(t, dict) else None)))
                }
                content = pick_system_prompt(tool_names)
                if snapshot:
                    content = content + "\n\n" + render_state(snapshot)
                messages.insert(0, {"role": "system", "content": content})

            tools: list[dict] = [_tool_to_dict(t) for t in (input.tools or [])]

            # B: local model + last message is a successful click_execute tool
            # result → the task already started; another LLM round here would hit
            # the just-evicted llama-server (or re-load it and evict the running
            # task). Reply with a canned confirmation and skip the LLM entirely.
            if is_local:
                submitted = _last_tool_result_is_execute_success(messages)
                if submitted is not None:
                    kind, ident = submitted
                    text = (_TASK_SUBMITTED_TEXT.format(task_id=ident) if kind == "task"
                            else _RUN_SUBMITTED_TEXT.format(run_id=ident))
                    yield encoder.encode(TextMessageChunkEvent(
                        message_id=uuid4().hex, role="assistant",
                        delta=text,
                    ))
                    return  # finally emits RUN_FINISHED (errored stays False)

            async def _consume(sess):
                nonlocal usage
                async for chunk in sess.stream(
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

            if is_local:
                # B2.5：本地 session 生命週期（enter→…→exit）釘在專屬 worker
                # thread——GPU gate 的 Condition.wait 不得凍住 event loop，且
                # gate 取放（thread-keyed 重入）必須發生在同一條執行緒。串流
                # 本身沿用 LocalChatSession.stream() 的 producer-thread 橋接。
                session_kwargs["gate_class"] = "agent"
                loop = asyncio.get_running_loop()
                ready: asyncio.Future = loop.create_future()
                done = threading.Event()

                def _set_ready(sess, exc):
                    if ready.done():
                        return
                    if exc is not None:
                        ready.set_exception(exc)
                    else:
                        ready.set_result(sess)

                def _session_worker():
                    try:
                        with self._chat.session(**session_kwargs) as sess:
                            loop.call_soon_threadsafe(_set_ready, sess, None)
                            # 持有 gate 直到 loop 端收尾。done 由 run() 的
                            # finally 設定——涵蓋 normal / CancelledError /
                            # GeneratorExit 全部 teardown 路徑。
                            done.wait()
                    except Exception as exc:
                        # enter 時期例外（gate 逾時 ModelBusyError、載入失敗）
                        # 橋回 loop，讓既有 except 分類接手。
                        loop.call_soon_threadsafe(_set_ready, None, exc)

                threading.Thread(
                    target=_session_worker, daemon=True, name="agent-session",
                ).start()
                try:
                    session = await ready
                    async for ev in _consume(session):
                        yield ev
                finally:
                    done.set()
            else:
                with self._chat.session(**session_kwargs) as session:
                    async for ev in _consume(session):
                        yield ev
        except GeneratorExit:
            # aclose()（消費者棄流）：async-gen 協定禁止在 GeneratorExit 後再
            # yield——標記 errored 讓 finally 跳過 RUN_FINISHED。worker 收尾由
            # 內層 finally 的 done.set() 完成；in-flight 生成由 kill_process 斷。
            errored = True
            if session is not None:
                session.kill_process()
            raise
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
            errored = True
        except NotImplementedError as e:
            # Provider does not yet support streaming tool calling
            # (Gemini — Wave 4.6 deliverable; Ollama done in Wave 4.7).
            yield encoder.encode(RunErrorEvent(
                code="agent.error.tools_not_supported",
                message=str(e),
            ))
            errored = True
        except ConnectionError as e:
            # Local llama-server torn down mid-request (model_manager evicted the
            # 'llm' slot for a task the agent just submitted). Surface a friendly
            # typed error instead of the raw ConnectionResetError [WinError 10054].
            # Remote providers aren't evicted — keep their connection errors generic.
            if is_local:
                yield encoder.encode(RunErrorEvent(
                    code="agent.error.model_busy", message=""))
            else:
                logger.exception("Agent run failed (remote connection error)")
                yield encoder.encode(RunErrorEvent(
                    code="agent.error.internal", message=str(e)))
            errored = True
        except Exception as e:
            logger.exception("Agent run failed")
            yield encoder.encode(RunErrorEvent(
                code="agent.error.internal", message=str(e)))
            errored = True
        finally:
            # AG-UI: a run ends with RUN_FINISHED (success) XOR RUN_ERROR (failure).
            # RUN_ERROR is terminal — do not emit a trailing RUN_FINISHED.
            # Cancel path (CancelledError) leaves errored=False and falls through
            # here, emitting RUN_FINISHED before CancelledError propagates — harmless
            # because the frontend abort() already tore down the stream client-side.
            if not errored:
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
