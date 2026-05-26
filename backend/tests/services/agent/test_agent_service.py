"""Tests for AgentService.run() and _resolve_model_choice().

Uses asyncio_mode="auto" (configured via pyproject.toml) — no @pytest.mark.asyncio needed.
"""
import asyncio
import json
import pytest
from contextlib import contextmanager
from unittest.mock import MagicMock
from ag_ui.core import UserMessage, SystemMessage, Tool
from app.services.agent.agent_service import AgentService, AgentError, _msg_to_dict, _tool_to_dict
from app.services.agent._ag_ui_compat import RunAgentInput


# ── Test helpers ─────────────────────────────────────────────────────

def _make_input(
    *,
    messages=None,
    tools=None,
    state=None,
    thread_id="t1",
    run_id="r1",
) -> RunAgentInput:
    """Construct a valid RunAgentInput with sensible defaults.

    RunAgentInput uses camelCase aliases (threadId / runId) via Pydantic
    alias_generator, but accepts snake_case constructor kwargs via model_config.
    forwardedProps (alias forwarded_props) is required by the SDK.
    """
    return RunAgentInput(
        thread_id=thread_id,
        run_id=run_id,
        messages=messages or [UserMessage(id="m0", content="hi")],
        tools=tools or [],
        state=state or {},
        context=[],
        forwarded_props={},
    )


# ── Fakes ─────────────────────────────────────────────────────────────

class FakeChatSession:
    """In-memory session that mimics LocalChatSession.stream() and kill_process()."""
    def __init__(self, chunks):
        self._chunks = chunks
        self.kill_called = False
        self.received_messages = None
        self.received_tools = None

    async def stream(self, messages, *, tools=None, max_tokens, temperature):
        # Records what was sent for assertions
        self.received_messages = messages
        self.received_tools = tools
        for c in self._chunks:
            yield c

    def kill_process(self):
        self.kill_called = True


class FakeChatService:
    """Mimics ChatService.session() context manager — both local and remote."""
    def __init__(self, chunks):
        self.last_session = None
        self.session_kwargs = None
        self._chunks = chunks

    @contextmanager
    def session(self, **kwargs):
        self.session_kwargs = kwargs
        self.last_session = FakeChatSession(self._chunks)
        try:
            yield self.last_session
        finally:
            pass


class FakeRemoteService:
    """Mimics RemoteService.get_provider_for_connection."""
    def __init__(self):
        self.provider_map = {}

    def get_provider_for_connection(self, conn_id, provider_name):
        return self.provider_map.get((conn_id, provider_name))


# ── _msg_to_dict / _tool_to_dict module-level helper tests ──────────

class TestMsgToDict:
    def test_plain_dict_passthrough(self):
        d = {"role": "user", "content": "hi"}
        result = _msg_to_dict(d)
        assert result == {"role": "user", "content": "hi"}

    def test_strips_id_from_plain_dict(self):
        d = {"role": "user", "content": "hi", "id": "sdk-internal-123"}
        result = _msg_to_dict(d)
        assert "id" not in result
        assert result["content"] == "hi"

    def test_pydantic_model_normalized(self):
        msg = UserMessage(id="m0", content="hello")
        result = _msg_to_dict(msg)
        assert result["role"] == "user"
        assert result["content"] == "hello"
        assert "id" not in result

    def test_system_message_normalized(self):
        msg = SystemMessage(id="s0", content="system prompt")
        result = _msg_to_dict(msg)
        assert result["role"] == "system"
        assert "id" not in result


class TestToolToDict:
    def test_plain_dict_passthrough(self):
        d = {"name": "navigate_to", "description": "nav", "parameters": {}}
        assert _tool_to_dict(d) == d

    def test_pydantic_tool_normalized(self):
        t = Tool(name="go", description="nav", parameters={})
        result = _tool_to_dict(t)
        assert result["name"] == "go"
        assert isinstance(result, dict)


# ── _resolve_model_choice tests ─────────────────────────────────────

class TestResolveModelChoice:
    def setup_method(self):
        self.remote = FakeRemoteService()
        self.svc = AgentService(chat_service=MagicMock(), remote_service=self.remote)

    def test_local_no_quant(self):
        assert self.svc._resolve_model_choice("qwen3:8b") == {
            "model_family": "qwen3", "model_size": "8b",
        }

    def test_local_with_quant(self):
        assert self.svc._resolve_model_choice("qwen3vl:8b:Q4_K_M") == {
            "model_family": "qwen3vl", "model_size": "8b", "quantization": "Q4_K_M",
        }

    # ── Remote choice: Phase-1 guard (Critical fix) ─────────────────────

    def test_remote_choice_rejected_with_friendly_error(self):
        """Phase 1: any remote: choice → agent.error.model_unavailable with message."""
        with pytest.raises(AgentError) as exc_info:
            self.svc._resolve_model_choice("remote:openai:3:gpt-4o-mini")
        assert exc_info.value.code == "agent.error.model_unavailable"
        assert "future update" in exc_info.value.message

    @pytest.mark.skip(reason="Wave 4 — remote streaming with tool calling not yet implemented")
    def test_remote_standard(self):
        """Wave 4 TODO: remote:openai:3:gpt-4o-mini → {remote_provider, remote_model}."""
        prov = MagicMock()
        self.remote.provider_map[(3, "openai")] = prov
        result = self.svc._resolve_model_choice("remote:openai:3:gpt-4o-mini")
        assert result == {"remote_provider": prov, "remote_model": "gpt-4o-mini"}

    @pytest.mark.skip(reason="Wave 4 — remote streaming with tool calling not yet implemented")
    def test_remote_model_id_with_colon(self):
        """Wave 4 TODO: model id like 'qwen3:8b-instruct' has colons inside."""
        prov = MagicMock()
        self.remote.provider_map[(5, "ollama")] = prov
        result = self.svc._resolve_model_choice("remote:ollama:5:qwen3:8b-instruct")
        assert result == {"remote_provider": prov, "remote_model": "qwen3:8b-instruct"}

    @pytest.mark.skip(reason="Wave 4 — remote streaming with tool calling not yet implemented")
    def test_remote_missing_provider(self):
        """Wave 4 TODO: provider not registered → model_unavailable."""
        with pytest.raises(AgentError, match="agent.error.model_unavailable"):
            self.svc._resolve_model_choice("remote:openai:999:foo")

    @pytest.mark.skip(reason="Wave 4 — remote streaming with tool calling not yet implemented")
    def test_invalid_remote_format(self):
        """Wave 4 TODO: too-short remote: string → no_model."""
        with pytest.raises(AgentError, match="agent.error.no_model"):
            self.svc._resolve_model_choice("remote:openai")  # missing parts

    @pytest.mark.skip(reason="Wave 4 — remote streaming with tool calling not yet implemented")
    def test_invalid_remote_conn_id(self):
        """Wave 4 TODO: non-numeric conn_id → no_model."""
        with pytest.raises(AgentError, match="agent.error.no_model"):
            self.svc._resolve_model_choice("remote:openai:abc:foo")  # conn_id NaN

    # ── Local empty-fragment validation (Important 1) ────────────────────

    def test_local_empty_size(self):
        """'qwen3:' — family present but empty size → no_model."""
        with pytest.raises(AgentError, match="agent.error.no_model"):
            self.svc._resolve_model_choice("qwen3:")

    def test_local_empty_family(self):
        """':8b' — missing family → no_model."""
        with pytest.raises(AgentError, match="agent.error.no_model"):
            self.svc._resolve_model_choice(":8b")

    def test_local_empty_size_with_quant(self):
        """'qwen3::Q4_K_M' — empty size segment → no_model."""
        with pytest.raises(AgentError, match="agent.error.no_model"):
            self.svc._resolve_model_choice("qwen3::Q4_K_M")

    def test_invalid_no_colon(self):
        with pytest.raises(AgentError, match="agent.error.no_model"):
            self.svc._resolve_model_choice("qwen3")  # no :


# ── run() happy path tests ───────────────────────────────────────────

class TestRunHappyPath:

    async def test_emits_run_started_and_finished_around_deltas(self):
        """Single text delta → RUN_STARTED + TEXT_MESSAGE_CHUNK + RUN_FINISHED."""
        chunks = [
            {"type": "delta", "message_id": "m1", "text": "hello"},
            {"type": "done", "usage": {"prompt_tokens": 10, "completion_tokens": 1}},
        ]
        chat = FakeChatService(chunks)
        svc = AgentService(chat_service=chat, remote_service=FakeRemoteService())

        inp = _make_input(
            messages=[UserMessage(id="m0", content="hi")],
            state={"agent_model_choice": "qwen3:8b"},
        )
        events = [e async for e in svc.run(inp, accept=None)]

        # event: RUN_STARTED, TEXT_MESSAGE_CHUNK, RUN_FINISHED = 3
        assert len(events) == 3
        assert "RUN_STARTED" in events[0]
        assert "runId" in events[0] and "threadId" in events[0]
        assert "TEXT_MESSAGE_CHUNK" in events[1]
        assert "messageId" in events[1]
        assert "hello" in events[1]
        assert "RUN_FINISHED" in events[2]
        assert "usage" in events[2]
        assert "promptTokens" in events[2]

    async def test_emits_tool_call_chunks(self):
        chunks = [
            {"type": "tool_call", "id": "tc1", "name": "navigate_to",
             "parent_message_id": "m1", "args_delta": '{"route":"/video"}'},
            {"type": "done", "usage": {"prompt_tokens": 5, "completion_tokens": 3}},
        ]
        chat = FakeChatService(chunks)
        svc = AgentService(chat_service=chat, remote_service=FakeRemoteService())
        inp = _make_input(
            messages=[UserMessage(id="m0", content="go to video")],
            tools=[Tool(name="navigate_to", description="nav", parameters={})],
            state={"agent_model_choice": "qwen3:8b"},
        )
        events = [e async for e in svc.run(inp)]
        # RUN_STARTED, TOOL_CALL_CHUNK, RUN_FINISHED
        assert any("TOOL_CALL_CHUNK" in e for e in events)
        assert any("navigate_to" in e for e in events)

    async def test_system_prompt_prepended_when_missing(self):
        chunks = [{"type": "done"}]
        chat = FakeChatService(chunks)
        svc = AgentService(chat_service=chat, remote_service=FakeRemoteService())
        inp = _make_input(
            messages=[UserMessage(id="m0", content="hi")],
            state={"agent_model_choice": "qwen3:8b"},
        )
        _ = [e async for e in svc.run(inp)]
        sent = chat.last_session.received_messages
        assert sent[0]["role"] == "system"
        assert "MediaTranX" in sent[0]["content"]
        # second message is the user message (normalized to dict)
        assert sent[1]["role"] == "user"
        assert sent[1]["content"] == "hi"

    async def test_system_prompt_not_duplicated(self):
        """If input messages already include a system role, don't prepend."""
        chunks = [{"type": "done"}]
        chat = FakeChatService(chunks)
        svc = AgentService(chat_service=chat, remote_service=FakeRemoteService())
        inp = _make_input(
            messages=[
                SystemMessage(id="s0", content="you are X"),
                UserMessage(id="m0", content="hi"),
            ],
            state={"agent_model_choice": "qwen3:8b"},
        )
        _ = [e async for e in svc.run(inp)]
        sent = chat.last_session.received_messages
        assert sent[0]["content"] == "you are X"
        assert len([m for m in sent if m["role"] == "system"]) == 1

    async def test_finished_carries_usage(self):
        chunks = [
            {"type": "delta", "message_id": "m1", "text": "x"},
            {"type": "done", "usage": {"prompt_tokens": 100, "completion_tokens": 50}},
        ]
        chat = FakeChatService(chunks)
        svc = AgentService(chat_service=chat, remote_service=FakeRemoteService())
        inp = _make_input(
            messages=[UserMessage(id="m0", content="hi")],
            state={"agent_model_choice": "qwen3:8b"},
        )
        events = [e async for e in svc.run(inp)]
        finished = events[-1]
        # Parse JSON to verify usage payload
        data_line = next(l[len("data: "):] for l in finished.split("\n") if l.startswith("data: "))
        payload = json.loads(data_line)
        assert payload["usage"]["promptTokens"] == 100
        assert payload["usage"]["completionTokens"] == 50

    async def test_session_kwargs_local(self):
        """session() receives correct kwargs for a local model choice."""
        chunks = [{"type": "done"}]
        chat = FakeChatService(chunks)
        svc = AgentService(chat_service=chat, remote_service=FakeRemoteService())
        inp = _make_input(
            messages=[UserMessage(id="m0", content="hi")],
            state={"agent_model_choice": "qwen3:8b"},
        )
        _ = [e async for e in svc.run(inp)]
        assert chat.session_kwargs == {"model_family": "qwen3", "model_size": "8b"}

    async def test_session_kwargs_local_with_quant(self):
        chunks = [{"type": "done"}]
        chat = FakeChatService(chunks)
        svc = AgentService(chat_service=chat, remote_service=FakeRemoteService())
        inp = _make_input(
            messages=[UserMessage(id="m0", content="hi")],
            state={"agent_model_choice": "qwen3vl:8b:Q4_K_M"},
        )
        _ = [e async for e in svc.run(inp)]
        assert chat.session_kwargs == {
            "model_family": "qwen3vl", "model_size": "8b", "quantization": "Q4_K_M",
        }


# ── Error path tests ────────────────────────────────────────────────

class TestRunErrors:

    async def test_no_model_emits_run_error(self):
        chat = FakeChatService([])
        svc = AgentService(chat_service=chat, remote_service=FakeRemoteService())
        inp = _make_input(
            messages=[UserMessage(id="m0", content="hi")],
            state={},  # no agent_model_choice
        )
        events = [e async for e in svc.run(inp)]
        assert any("RUN_ERROR" in e and "agent.error.no_model" in e for e in events)
        # RUN_FINISHED still emitted (finally block)
        assert "RUN_FINISHED" in events[-1]

    async def test_empty_messages_rejected(self):
        """input.messages=[] → RunErrorEvent(agent.error.internal, 'empty messages list')."""
        chat = FakeChatService([])
        svc = AgentService(chat_service=chat, remote_service=FakeRemoteService())
        inp = _make_input(
            messages=[],  # override default
            state={"agent_model_choice": "qwen3:8b"},
        )
        # Override messages to be truly empty (default helper provides one)
        inp.messages = []
        events = [e async for e in svc.run(inp)]
        assert any(
            "RUN_ERROR" in e and "agent.error.internal" in e and "empty messages list" in e
            for e in events
        )
        assert "RUN_FINISHED" in events[-1]

    async def test_unknown_exception_emits_internal_error(self):
        """If session.stream raises an unexpected exception, RUN_ERROR with internal."""
        class BoomSession:
            async def stream(self, **kwargs):
                raise RuntimeError("upstream blowup")
                yield  # unreachable but keeps it a gen

            def kill_process(self):
                pass

        class BoomChat:
            @contextmanager
            def session(self, **kwargs):
                yield BoomSession()

        svc = AgentService(chat_service=BoomChat(), remote_service=FakeRemoteService())
        inp = _make_input(
            messages=[UserMessage(id="m0", content="hi")],
            state={"agent_model_choice": "qwen3:8b"},
        )
        events = [e async for e in svc.run(inp)]
        assert any("RUN_ERROR" in e and "agent.error.internal" in e for e in events)
        assert any("upstream blowup" in e for e in events)


# ── Cancel test ─────────────────────────────────────────────────────

class TestRunCancel:

    async def test_cancelled_invokes_kill_and_reraises(self):
        """CancelledError mid-stream → session.kill_process() called + re-raised."""
        kill_recorded = {"called": False}

        async def cancel_after_one_chunk():
            yield {"type": "delta", "message_id": "m1", "text": "x"}
            await asyncio.sleep(0)  # checkpoint where cancel can land
            raise asyncio.CancelledError()

        class CancelSession:
            def __init__(self):
                self._gen = cancel_after_one_chunk()

            async def stream(self, **kwargs):
                async for c in self._gen:
                    yield c

            def kill_process(self):
                kill_recorded["called"] = True

        class CancelChat:
            @contextmanager
            def session(self, **kwargs):
                yield CancelSession()

        svc = AgentService(chat_service=CancelChat(), remote_service=FakeRemoteService())
        inp = _make_input(
            messages=[UserMessage(id="m0", content="hi")],
            state={"agent_model_choice": "qwen3:8b"},
        )
        with pytest.raises(asyncio.CancelledError):
            async for _ in svc.run(inp):
                pass
        assert kill_recorded["called"] is True
