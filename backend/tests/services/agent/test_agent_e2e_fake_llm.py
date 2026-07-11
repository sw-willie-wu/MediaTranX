"""Wave 1 Task 1.6 — fake-LLM end-to-end smoke tests.

Strategy: override *chat_service* in AppContainer so the real AgentService,
real FastAPI route, and real StreamingResponse all run.  Only the
ChatService.session() context manager is faked — it yields a FakeChatSession
whose stream() returns predetermined chunks.  This gives maximum e2e coverage
without spawning a real llama-server process.

Coverage this file adds over existing unit tests:
- Real AgentService.run() driving a real HTTP POST via TestClient
- Real FastAPI route + StreamingResponse SSE framing verified at the wire level
- Real container.chat_service.override() + container.agent_service re-wiring path
- cancel propagation: FakeSession.kill_called spy verifies the hook fires
- multi-round warm-pool: two sequential POSTs verify kill is NOT called between rounds

NOT re-tested here (covered by earlier Wave 1 unit tests):
- LocalChatSession async↔sync bridge threading (test_chat_service_stream.py)
- LlamaServer.chat_stream() SSE parser (test_llama_server_chat_stream.py)
- _resolve_model_choice / _msg_to_dict / _tool_to_dict (test_agent_service.py)
"""
from __future__ import annotations

import json
from contextlib import contextmanager

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.init.container import AppContainer
from app.services.agent.agent_service import AgentService
from app.services.setup.remote_service import RemoteService


# ---------------------------------------------------------------------------
# Fake session + service
# ---------------------------------------------------------------------------

class FakeChatSession:
    """Minimal LocalChatSession stand-in.

    - stream() is an async generator that yields predetermined chunks.
    - kill_process() records that it was called (for cancel / warm-pool tests).
    """

    def __init__(self, chunks: list[dict]):
        self._chunks = chunks
        self.kill_called = False
        self.received_messages: list[dict] | None = None
        self.received_tools: list[dict] | None = None

    async def stream(
        self,
        messages: list[dict],
        *,
        tools=None,
        max_tokens: int,
        temperature: float,
    ):
        self.received_messages = messages
        self.received_tools = tools
        for chunk in self._chunks:
            yield chunk

    def kill_process(self) -> None:
        self.kill_called = True


class FakeChatService:
    """Minimal ChatService stand-in.

    Yields a FakeChatSession whose chunks are set at construction time.
    Stores the last session and session kwargs for assertion access.
    """

    def __init__(self, chunks: list[dict]):
        self._chunks = chunks
        self.last_session: FakeChatSession | None = None
        self.session_kwargs: dict | None = None

    @contextmanager
    def session(self, **kwargs):
        self.session_kwargs = kwargs
        sess = FakeChatSession(self._chunks)
        self.last_session = sess
        try:
            yield sess
        finally:
            pass


# ---------------------------------------------------------------------------
# Preset chunk sequences
# ---------------------------------------------------------------------------

# Two text delta chunks + done with usage
TEXT_CHUNKS = [
    {"type": "delta", "message_id": "msg1", "text": "Hello"},
    {"type": "delta", "message_id": "msg1", "text": " world!"},
    {"type": "done", "usage": {"prompt_tokens": 50, "completion_tokens": 2}},
]

# A single tool-call chunk + done
TOOL_CHUNKS = [
    {
        "type": "tool_call",
        "id": "tc1",
        "name": "navigate_to",
        "parent_message_id": "msg1",
        "args_delta": '{"route":"/video"}',
    },
    {"type": "done", "usage": {"prompt_tokens": 100, "completion_tokens": 5}},
]

# Just done (minimal happy path)
MINIMAL_CHUNKS = [
    {"type": "done", "usage": {"prompt_tokens": 10, "completion_tokens": 0}},
]


# ---------------------------------------------------------------------------
# App builder helper
# ---------------------------------------------------------------------------

@contextmanager
def _build_app_with_fake_chat(fake_chat):
    """Context manager: build a minimal FastAPI app with real AgentService + fake chat_service.

    The key difference from test_agent_route.py (which overrides agent_service):
    here we override *chat_service* so the real AgentService runs end-to-end.

    Yields (app, container, fake_chat) and guarantees teardown (unwire +
    reset_override) in its own finally block — no leak even if wire() raises.
    """
    container = AppContainer()

    # Inject the fake chat service provider
    container.chat_service.override(fake_chat)

    # Build a real AgentService instance wired to the fake chat + real remote
    real_remote = RemoteService()
    real_agent = AgentService(
        chat_service=fake_chat,
        remote_service=real_remote,
    )
    container.agent_service.override(real_agent)

    from app.api.routes.agent import router as agent_router

    app = FastAPI()
    app.include_router(agent_router, prefix="/agent")
    container.wire(modules=["app.api.routes.agent.run"])

    try:
        yield app, container, fake_chat
    finally:
        container.unwire()
        container.chat_service.reset_override()
        container.agent_service.reset_override()


# ---------------------------------------------------------------------------
# Request body builder
# ---------------------------------------------------------------------------

def _body(
    text: str = "hello",
    thread_id: str = "t1",
    run_id: str = "r1",
    model_choice: str = "qwen3:8b",
    tools: list | None = None,
) -> dict:
    """Wire-format POST body (camelCase aliases)."""
    return {
        "threadId": thread_id,
        "runId": run_id,
        "messages": [{"id": "m0", "role": "user", "content": text}],
        "tools": tools if tools is not None else [],
        "state": {"agent_model_choice": model_choice},
        "context": [],
        "forwardedProps": {},
    }


# ---------------------------------------------------------------------------
# Helper: parse SSE body into list of (event_type, data_dict) tuples
# ---------------------------------------------------------------------------

def _parse_sse(body: str) -> list[tuple[str, dict]]:
    """Parse a raw SSE body string into (event_type, data_dict) pairs.

    ag-ui EventEncoder emits data-only SSE lines — no separate 'event:' line.
    The event type lives inside the JSON payload as the 'type' field:

        data: {"type":"RUN_STARTED","threadId":"t1","runId":"r1"}

        data: {"type":"TEXT_MESSAGE_CHUNK","messageId":"m1","delta":"Hi"}

    Returns a list of (type_string, full_data_dict) in emission order.
    """
    result: list[tuple[str, dict]] = []
    for line in body.splitlines():
        if not line.startswith("data: "):
            continue
        data_str = line[len("data: "):]
        try:
            payload = json.loads(data_str)
        except json.JSONDecodeError:
            pytest.fail(f"Malformed SSE data line: {line!r}")
        event_type = payload.get("type", "UNKNOWN")
        result.append((event_type, payload))
    return result


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestAgentE2EFakeLLM:

    # ── Happy path: text-only ────────────────────────────────────────────

    def test_happy_path_text_only(self):
        """Route → real AgentService → fake session → SSE wire format verified.

        Asserts:
        - HTTP 200 with text/event-stream content-type
        - SSE body: RUN_STARTED first, then TEXT_MESSAGE_CHUNKs, then RUN_FINISHED last
        - camelCase wire fields: runId / threadId / messageId / delta
        - RUN_FINISHED carries usage with promptTokens / completionTokens
        """
        fake_chat = FakeChatService(TEXT_CHUNKS)
        with _build_app_with_fake_chat(fake_chat) as (app, container, fake_chat):
            client = TestClient(app)
            resp = client.post("/agent/run", json=_body())

            assert resp.status_code == 200
            assert resp.headers["content-type"].startswith("text/event-stream")

            events = _parse_sse(resp.text)
            types = [t for t, _ in events]

            # First event must be RUN_STARTED
            assert types[0] == "RUN_STARTED"
            # Last event must be RUN_FINISHED
            assert types[-1] == "RUN_FINISHED"

            # TEXT_CHUNKS has exactly 2 delta entries → exactly 2 TEXT_MESSAGE_CHUNK events
            text_events = [(t, d) for t, d in events if t == "TEXT_MESSAGE_CHUNK"]
            assert len(text_events) == 2

            # Verify camelCase wire fields on first text event
            _, first_text_data = text_events[0]
            assert "messageId" in first_text_data
            assert "delta" in first_text_data
            assert first_text_data["delta"] == "Hello"

            # RUN_STARTED has runId + threadId
            _, started_data = events[0]
            assert started_data.get("runId") == "r1"
            assert started_data.get("threadId") == "t1"

            # RUN_FINISHED carries usage
            _, finished_data = events[-1]
            assert "usage" in finished_data
            assert finished_data["usage"]["promptTokens"] == 50
            assert finished_data["usage"]["completionTokens"] == 2

    # ── Happy path: tool call ────────────────────────────────────────────

    def test_happy_path_with_tool_call(self):
        """Tool-call chunks emitted via TOOL_CALL_CHUNK with correct wire fields.

        Verifies:
        - TOOL_CALL_CHUNK present in SSE body
        - camelCase wire fields: toolCallId / toolCallName / parentMessageId / delta
        - toolCallName == 'navigate_to'
        - delta contains the args fragment

        Note: ag_ui Tool uses a flat schema {name, description, parameters},
        NOT the OpenAI nested {type:"function", function:{name, ...}} shape.
        """
        navigate_tool = {
            "name": "navigate_to",
            "description": "Navigate to a top-level domain view.",
            "parameters": {
                "type": "object",
                "properties": {"route": {"type": "string"}},
                "required": ["route"],
            },
        }
        fake_chat = FakeChatService(TOOL_CHUNKS)
        with _build_app_with_fake_chat(fake_chat) as (app, container, fake_chat):
            client = TestClient(app)
            resp = client.post(
                "/agent/run",
                json=_body(text="go to video", tools=[navigate_tool]),
            )

            assert resp.status_code == 200
            events = _parse_sse(resp.text)
            types = [t for t, _ in events]

            assert "TOOL_CALL_CHUNK" in types
            _, tool_data = next((t, d) for t, d in events if t == "TOOL_CALL_CHUNK")
            # Wire-format camelCase fields
            assert tool_data.get("toolCallName") == "navigate_to"
            assert "toolCallId" in tool_data
            assert "parentMessageId" in tool_data
            assert "/video" in tool_data.get("delta", "")

    # ── System prompt prepend ────────────────────────────────────────────

    def test_system_prompt_prepended_to_messages(self):
        """When no system message in input, AgentService must prepend AGENT_SYSTEM_PROMPT.

        Verifies the real AgentService._msg_to_dict + system-prepend guard runs
        (not the unit test's direct svc.run() call — this time via HTTP route).
        """
        # _body() 不宣告工具（tools: []）→ 動態組合選精簡版（pipeline-feature-gate §3.4）
        from app.services.agent._system_prompt import AGENT_SYSTEM_PROMPT_NO_PIPELINE

        fake_chat = FakeChatService(MINIMAL_CHUNKS)
        with _build_app_with_fake_chat(fake_chat) as (app, container, fake_chat):
            client = TestClient(app)
            resp = client.post("/agent/run", json=_body(text="do something"))
            assert resp.status_code == 200

            assert fake_chat.last_session is not None
            received = fake_chat.last_session.received_messages
            assert received is not None
            # First message must be system prompt
            assert received[0]["role"] == "system"
            assert received[0]["content"] == AGENT_SYSTEM_PROMPT_NO_PIPELINE
            # Second message is the user input
            assert received[1]["role"] == "user"
            assert received[1]["content"] == "do something"

    # ── Error path: no model choice ──────────────────────────────────────

    def test_error_path_no_model_emits_run_error(self):
        """state without agent_model_choice → AgentError → lone terminal RUN_ERROR.

        Verifies:
        - HTTP 200 (errors are streamed as SSE, not HTTP error codes)
        - RUN_ERROR present with agent.error.no_model code
        - RUN_ERROR is terminal — no trailing RUN_FINISHED (AG-UI conformance)
        """
        fake_chat = FakeChatService([])  # session never opened
        with _build_app_with_fake_chat(fake_chat) as (app, container, fake_chat):
            body = _body()
            body["state"] = {}  # no agent_model_choice
            client = TestClient(app)
            resp = client.post("/agent/run", json=body)

            assert resp.status_code == 200
            events = _parse_sse(resp.text)
            types = [t for t, _ in events]

            assert "RUN_ERROR" in types
            _, error_data = next((t, d) for t, d in events if t == "RUN_ERROR")
            assert error_data.get("code") == "agent.error.no_model"

            # RUN_ERROR is terminal — no trailing RUN_FINISHED (AG-UI conformance)
            assert types[-1] == "RUN_ERROR"
            assert "RUN_FINISHED" not in types

    # ── Cancel: kill_process spy ─────────────────────────────────────────

    def test_cancel_propagates_kill_process(self):
        """CancelledError mid-stream → AgentService.run() calls session.kill_process().

        Approach: FakeSession.stream() raises asyncio.CancelledError after the
        first chunk.  AgentService.run()'s except CancelledError block must call
        session.kill_process() before re-raising.

        Because TestClient runs ASGI synchronously and streams the full body
        before returning, we verify the spy flag via CancelSession below.
        The CancelledError re-raise causes the StreamingResponse to close early
        — TestClient still returns a response (partial body) with the initial
        RUN_STARTED event and the kill_called flag set.
        """
        import asyncio

        kill_spy: list[bool] = [False]

        class CancelFakeChatSession:
            """Yields one chunk then raises CancelledError; records kill call."""
            def __init__(self):
                self.kill_called = False

            async def stream(self, messages, *, tools=None, max_tokens, temperature):
                yield {"type": "delta", "message_id": "m1", "text": "starting"}
                raise asyncio.CancelledError()

            def kill_process(self):
                self.kill_called = True
                kill_spy[0] = True

        class CancelFakeChatService:
            def __init__(self):
                self.last_session = None

            @contextmanager
            def session(self, **kwargs):
                sess = CancelFakeChatSession()
                self.last_session = sess
                try:
                    yield sess
                finally:
                    pass

        cancel_chat = CancelFakeChatService()
        with _build_app_with_fake_chat(cancel_chat) as (app, container, _):
            client = TestClient(app, raise_server_exceptions=False)
            # CancelledError is re-raised inside the generator; StreamingResponse
            # closes the stream. TestClient still returns a 200 with partial body.
            resp = client.post("/agent/run", json=_body())
            # Response is 200 (headers sent before body) or 500 — either way
            # the kill_process spy must have fired.
            assert kill_spy[0] is True, "kill_process() was not called on cancel"

    # ── Multi-round warm-pool ────────────────────────────────────────────

    def test_two_sequential_rounds_both_succeed(self):
        """Two sequential POSTs both return 200 + RUN_FINISHED, and AgentService
        does not call kill_process between rounds on a clean exit.

        Verifies AgentService doesn't call kill_process on clean exit; round 2
        reuses container/router state correctly (fresh FakeChatSession per call,
        but no state pollution from round 1).
        """
        fake_chat = FakeChatService(TEXT_CHUNKS)
        with _build_app_with_fake_chat(fake_chat) as (app, container, fake_chat):
            client = TestClient(app)

            # Round 1
            resp1 = client.post(
                "/agent/run",
                json=_body(text="round one", thread_id="t1", run_id="r1"),
            )
            assert resp1.status_code == 200
            assert "RUN_FINISHED" in resp1.text
            events1 = _parse_sse(resp1.text)
            assert events1[-1][0] == "RUN_FINISHED"

            # After clean stream (SENTINEL_END), kill_process must NOT be called
            # (warm-pool safety invariant from chat_service.py comment).
            # FakeChatSession doesn't call kill_process on clean exit — verify spy.
            session_after_r1 = fake_chat.last_session
            assert session_after_r1 is not None
            assert session_after_r1.kill_called is False, (
                "kill_process() was called after a clean round-1 stream exit — "
                "warm-pool safety invariant violated"
            )

            # Round 2 — FakeChatService creates a fresh session; must also succeed
            resp2 = client.post(
                "/agent/run",
                json=_body(text="round two", thread_id="t1", run_id="r2"),
            )
            assert resp2.status_code == 200
            assert "RUN_FINISHED" in resp2.text
            events2 = _parse_sse(resp2.text)
            assert events2[-1][0] == "RUN_FINISHED"
            # TEXT_CHUNKS has exactly 2 delta entries → exactly 2 TEXT_MESSAGE_CHUNK events
            text_types2 = [t for t, _ in events2 if t == "TEXT_MESSAGE_CHUNK"]
            assert len(text_types2) == 2

    # ── No-cache SSE headers ─────────────────────────────────────────────

    def test_sse_no_cache_headers_present(self):
        """Real route sets Cache-Control: no-cache + X-Accel-Buffering: no."""
        fake_chat = FakeChatService(MINIMAL_CHUNKS)
        with _build_app_with_fake_chat(fake_chat) as (app, container, fake_chat):
            client = TestClient(app)
            resp = client.post("/agent/run", json=_body())

            assert resp.status_code == 200
            assert resp.headers.get("cache-control") == "no-cache"
            assert resp.headers.get("x-accel-buffering") == "no"
