"""B2.5 T4：agent 本地 session 生命週期（enter→stream→exit）釘在專屬 worker thread。

- gate 取放必須同執行緒（thread-keyed 重入），enter/exit 不得跑在 event loop 上。
- teardown 訊號走 finally：normal / CancelledError / GeneratorExit 都要讓 worker 收尾。
- enter 時期例外（gate 逾時 ModelBusyError ⊂ ConnectionError）要橋回 loop 的
  except ConnectionError → agent.error.model_busy。
"""
import asyncio
import threading
import time
from contextlib import contextmanager

from ag_ui.core import UserMessage

from app.handler.exceptions import ModelBusyError
from app.services.agent._ag_ui_compat import RunAgentInput
from app.services.agent.agent_service import AgentService


def _make_input(state=None):
    return RunAgentInput(
        thread_id="t1",
        run_id="r1",
        messages=[UserMessage(id="m0", content="hi")],
        tools=[],
        state=state or {"agent_model_choice": "qwen3:8b"},
        context=[],
        forwarded_props={},
    )


class ThreadRecordingSession:
    def __init__(self, chunks):
        self._chunks = chunks
        self.kill_called = False

    async def stream(self, messages, *, tools=None, max_tokens, temperature):
        for c in self._chunks:
            yield c

    def kill_process(self):
        self.kill_called = True


class ThreadRecordingChatService:
    def __init__(self, chunks, enter_exc=None):
        self.enter_tid = None
        self.exit_tid = None
        self.exited = threading.Event()
        self.session_kwargs = None
        self._chunks = chunks
        self._enter_exc = enter_exc
        self.last_session = None

    @contextmanager
    def session(self, **kwargs):
        self.session_kwargs = kwargs
        self.enter_tid = threading.get_ident()
        if self._enter_exc is not None:
            raise self._enter_exc
        self.last_session = ThreadRecordingSession(self._chunks)
        try:
            yield self.last_session
        finally:
            self.exit_tid = threading.get_ident()
            self.exited.set()


_CHUNKS = [
    {"type": "delta", "message_id": "m1", "text": "hello"},
    {"type": "done", "usage": None},
]


async def _collect(gen):
    return [ev async for ev in gen]


async def test_local_session_enter_exit_on_worker_thread():
    chat = ThreadRecordingChatService(_CHUNKS)
    svc = AgentService(chat, remote_service=None)
    loop_tid = threading.get_ident()

    events = await _collect(svc.run(_make_input()))

    assert chat.exited.wait(timeout=5)
    assert chat.enter_tid is not None
    assert chat.enter_tid == chat.exit_tid, "gate 取放必須同執行緒"
    assert chat.enter_tid != loop_tid, "session enter 不得跑在 event loop 執行緒"
    joined = "".join(events)
    assert "RUN_FINISHED" in joined or "run_finished" in joined.lower()


async def test_gate_class_agent_passed_for_local():
    chat = ThreadRecordingChatService(_CHUNKS)
    svc = AgentService(chat, remote_service=None)
    await _collect(svc.run(_make_input()))
    assert chat.session_kwargs.get("gate_class") == "agent"


async def test_session_exit_on_consumer_abandon():
    chat = ThreadRecordingChatService([
        {"type": "delta", "message_id": "m1", "text": "a"},
        {"type": "delta", "message_id": "m1", "text": "b"},
        {"type": "done", "usage": None},
    ])
    svc = AgentService(chat, remote_service=None)
    gen = svc.run(_make_input())
    # 只消費前兩個事件就 aclose（GeneratorExit 路徑）
    await gen.__anext__()
    await gen.__anext__()
    await gen.aclose()
    assert chat.exited.wait(timeout=5), "abandon 後 worker 必須收尾（finally 訊號）"
    assert chat.enter_tid == chat.exit_tid


async def test_enter_time_model_busy_bridges_to_run_error():
    chat = ThreadRecordingChatService(_CHUNKS, enter_exc=ModelBusyError("busy"))
    svc = AgentService(chat, remote_service=None)
    events = await _collect(svc.run(_make_input()))
    joined = "".join(events)
    assert "agent.error.model_busy" in joined


async def test_no_orphan_worker_thread_after_run():
    chat = ThreadRecordingChatService(_CHUNKS)
    svc = AgentService(chat, remote_service=None)
    await _collect(svc.run(_make_input()))
    assert chat.exited.wait(timeout=5)
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        if not any(t.name == "agent-session" and t.is_alive() for t in threading.enumerate()):
            return
        await asyncio.sleep(0.05)
    raise AssertionError("agent-session worker thread leaked")
