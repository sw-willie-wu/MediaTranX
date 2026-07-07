"""GPU inference gate（spec B2.5）：全域序列化、每執行緒重入、非對稱逾時、免洩漏。"""
import threading
import time

import pytest

from app.adapters.ai import model_manager as mm_module
from app.adapters.ai.model_manager import ModelManager
from app.handler.exceptions import ModelBusyError


class FakeRuntime:
    def __init__(self, slot):
        self.slot = slot
        self._loaded = False
        self._config = None
        self.fail_next_load = False

    def is_loaded(self):
        return self._loaded

    def get_current_config(self):
        return self._config

    def _resolve_model_path(self, model_id, variant, mm):
        return f"/fake/{model_id}", {}

    def load(self, path, config, on_progress=None):
        if self.fail_next_load:
            self.fail_next_load = False
            raise RuntimeError("load boom")
        self._loaded = True
        self._config = config

    def unload(self):
        self._loaded = False
        self._config = None


def _mm_with(*slots):
    mm = ModelManager()
    for s in slots:
        mm.register_runtime(FakeRuntime(s))
    return mm


def test_gate_serializes_across_threads():
    mm = _mm_with("a", "b")
    order = []
    a_inside = threading.Event()
    release_a = threading.Event()

    def hold_a():
        with mm.acquire("a", "m1"):
            order.append("a-start")
            a_inside.set()
            release_a.wait(timeout=5)
            order.append("a-end")

    def want_b():
        a_inside.wait(timeout=5)
        with mm.acquire("b", "m2"):
            order.append("b-start")

    ta = threading.Thread(target=hold_a)
    tb = threading.Thread(target=want_b)
    ta.start(); tb.start()
    a_inside.wait(timeout=5)
    time.sleep(0.2)          # b 必須還在 gate 外等
    assert order == ["a-start"]
    release_a.set()
    ta.join(timeout=5); tb.join(timeout=5)
    assert order == ["a-start", "a-end", "b-start"]


def test_agent_class_times_out_with_model_busy(monkeypatch):
    monkeypatch.setitem(mm_module.GATE_TIMEOUTS, "agent", 0.2)
    mm = _mm_with("a", "llm")
    a_inside = threading.Event()
    release_a = threading.Event()

    def hold_a():
        with mm.acquire("a", "m1"):
            a_inside.set()
            release_a.wait(timeout=5)

    ta = threading.Thread(target=hold_a)
    ta.start()
    a_inside.wait(timeout=5)
    with pytest.raises(ModelBusyError):
        with mm.acquire("llm", "qwen", gate_class="agent"):
            pass
    release_a.set()
    ta.join(timeout=5)


def test_model_busy_is_connection_error():
    # agent 路徑靠 except ConnectionError → agent.error.model_busy 映射
    assert issubclass(ModelBusyError, ConnectionError)


def test_same_thread_reentrancy_nested_acquire():
    mm = _mm_with("a", "b")
    with mm.acquire("a", "m1"):
        with mm.acquire("b", "m2"):   # 同執行緒巢狀（doc_ocr 型）不可自死鎖
            pass


def test_gpu_session_then_acquire_nested():
    mm = _mm_with("a")
    with mm.gpu_session():
        with mm.acquire("a", "m1"):
            pass


def test_gate_released_on_load_failure():
    mm = ModelManager()
    rt = FakeRuntime("a")
    rt.fail_next_load = True
    mm.register_runtime(rt)
    with pytest.raises(RuntimeError):
        with mm.acquire("a", "m1"):
            pass
    # gate 未洩漏：另一執行緒能立刻取得
    ok = threading.Event()

    def try_acquire():
        with mm.acquire("a", "m1"):
            ok.set()

    t = threading.Thread(target=try_acquire)
    t.start(); t.join(timeout=3)
    assert ok.is_set()


def test_task_class_waits_and_succeeds(monkeypatch):
    monkeypatch.setitem(mm_module.GATE_TIMEOUTS, "task", 5.0)
    mm = _mm_with("a", "b")
    a_inside = threading.Event()
    got_b = threading.Event()

    def hold_a_briefly():
        with mm.acquire("a", "m1"):
            a_inside.set()
            time.sleep(0.3)

    def want_b():
        a_inside.wait(timeout=5)
        with mm.acquire("b", "m2", gate_class="task"):
            got_b.set()

    ta = threading.Thread(target=hold_a_briefly)
    tb = threading.Thread(target=want_b)
    ta.start(); tb.start()
    ta.join(timeout=5); tb.join(timeout=5)
    assert got_b.is_set()
