"""Unit tests for ChatService.session() + ChatSession."""
import pytest
from contextlib import contextmanager
from unittest.mock import MagicMock

from app.services.llm.chat_service import ChatService


@contextmanager
def _fake_acquire_ctx(*args, **kwargs):
    yield None  # ModelManager.acquire returns the runtime; we yield None since test passes the wrapper directly


def _fake_llama_runtime() -> MagicMock:
    """LlmWrapper-shaped mock with acquire as a contextmanager and chat/complete + _model._process."""
    rt = MagicMock()
    rt.acquire = MagicMock(side_effect=lambda *a, **kw: _fake_acquire_ctx())
    rt.chat = MagicMock(return_value="chat-text")
    rt.complete = MagicMock(return_value="completion-text")
    rt._model = MagicMock()
    rt._model._process = MagicMock()
    return rt


@contextmanager
def _emitting_acquire_ctx(raw_values, **kwargs):
    """Acquire stand-in that fires on_progress with raw model-load fractions
    on entry, mimicking the LlamaServer load lifecycle."""
    cb = kwargs.get("on_progress")
    if cb is not None:
        for v in raw_values:
            cb(v, "task.progress.waiting_model_load|x")
    yield None


def _emitting_llama_runtime(raw_values) -> MagicMock:
    rt = MagicMock()
    rt.acquire = MagicMock(
        side_effect=lambda *a, **kw: _emitting_acquire_ctx(raw_values, **kw)
    )
    rt._model = MagicMock()
    rt._model._process = MagicMock()
    return rt


def test_session_acquires_and_releases():
    rt = _fake_llama_runtime()
    svc = ChatService(rt)
    with svc.session(model_family="gemma4", model_size="4b") as session:
        assert session is not None
    rt.acquire.assert_called_once()


def test_session_chat_forwards_to_runtime():
    rt = _fake_llama_runtime()
    svc = ChatService(rt)
    with svc.session(model_family="gemma4", model_size="4b") as session:
        out = session.chat(
            messages=[{"role": "user", "content": "hi"}],
            max_tokens=100, temperature=0.1,
        )
    assert out == "chat-text"
    rt.chat.assert_called_once()


def test_session_complete_forwards_to_runtime():
    rt = _fake_llama_runtime()
    svc = ChatService(rt)
    with svc.session(model_family="qwen3", model_size="4b") as session:
        out = session.complete(
            prompt="say hi", max_tokens=100, temperature=0.1,
        )
    assert out == "completion-text"
    rt.complete.assert_called_once()


def test_session_kill_process_routes_through_server_stop():
    rt = _fake_llama_runtime()
    svc = ChatService(rt)
    with svc.session(model_family="gemma4", model_size="4b") as session:
        # kill_process now clears rt._model after stop (so wrapper.is_loaded()
        # stops lying); capture the model ref upfront to keep the assertion.
        model_before_kill = rt._model
        session.kill_process()
    model_before_kill.stop.assert_called_once_with(timeout=2.0)
    assert rt._model is None  # cleared


def test_session_kill_process_safe_when_no_process():
    """kill_process is a best-effort hook — no-op if runtime not yet loaded or process gone."""
    rt = _fake_llama_runtime()
    rt._model = None  # not loaded
    svc = ChatService(rt)
    with svc.session(model_family="gemma4", model_size="4b") as session:
        session.kill_process()  # must not raise


def test_chat_with_images_builds_openai_compat_payload(tmp_path):
    """chat_with_images sends OpenAI-style messages with image_url data URIs."""
    rt = _fake_llama_runtime()
    svc = ChatService(rt)

    # Create a tiny test image
    from PIL import Image
    img_path = tmp_path / "tiny.png"
    Image.new("RGB", (8, 8), (128, 0, 0)).save(img_path)

    with svc.session(model_family="qwen3vl", model_size="2b") as session:
        session.chat_with_images(
            prompt="describe", images=[img_path], max_tokens=16, temperature=0.0,
        )

    # Inspect the messages payload sent to runtime.chat
    args, kwargs = rt.chat.call_args
    messages = kwargs["messages"]
    assert isinstance(messages, list)
    assert messages[0]["role"] == "user"
    content = messages[0]["content"]
    assert isinstance(content, list)
    assert any(part["type"] == "text" for part in content)
    image_parts = [p for p in content if p["type"] == "image_url"]
    assert len(image_parts) == 1
    url = image_parts[0]["image_url"]["url"]
    assert url.startswith("data:image/png;base64,")


def test_one_shot_chat_still_works():
    """Backward-compat: ChatService.chat(prompt, ...) (one-shot) opens its own session."""
    rt = _fake_llama_runtime()
    svc = ChatService(rt)
    out = svc.chat("hi", model_family="gemma4", model_size="4b",
                   max_tokens=100, temperature=0.1)
    assert out == "chat-text"
    rt.acquire.assert_called_once()


# ── load_band: model-load progress scaling ───────────────────────────────

def test_load_band_scales_raw_fraction_into_band():
    rt = _emitting_llama_runtime([0.05, 0.2, 0.9, 1.0])
    svc = ChatService(rt)
    received = []
    with svc.session(
        model_family="gemma4", model_size="4b",
        on_load_progress=lambda p, m: received.append(p),
        load_band=(0.50, 0.55),
    ):
        pass
    # 0.50 + raw * 0.05
    assert received == [
        pytest.approx(0.5025), pytest.approx(0.51),
        pytest.approx(0.545), pytest.approx(0.55),
    ]


def test_load_band_none_passes_raw_unscaled():
    rt = _emitting_llama_runtime([0.05, 0.2, 1.0])
    svc = ChatService(rt)
    received = []
    with svc.session(
        model_family="gemma4", model_size="4b",
        on_load_progress=lambda p, m: received.append(p),
        load_band=None,
    ):
        pass
    assert received == [pytest.approx(0.05), pytest.approx(0.2), pytest.approx(1.0)]


def test_load_band_clamps_out_of_range_raw():
    rt = _emitting_llama_runtime([-0.5, 1.5])
    svc = ChatService(rt)
    received = []
    with svc.session(
        model_family="gemma4", model_size="4b",
        on_load_progress=lambda p, m: received.append(p),
        load_band=(0.70, 0.72),
    ):
        pass
    assert received == [pytest.approx(0.70), pytest.approx(0.72)]


def test_load_band_without_callback_does_not_crash():
    rt = _emitting_llama_runtime([0.05, 1.0])
    svc = ChatService(rt)
    with svc.session(
        model_family="gemma4", model_size="4b",
        on_load_progress=None, load_band=(0.50, 0.55),
    ):
        pass  # must not raise; acquire still called
    rt.acquire.assert_called_once()


def test_load_band_ignored_on_remote_path():
    rt = _fake_llama_runtime()
    svc = ChatService(rt)
    with svc.session(
        remote_provider=MagicMock(), remote_model="gpt-4o-mini",
        on_load_progress=lambda p, m: None, load_band=(0.50, 0.55),
    ) as session:
        assert session is not None  # RemoteChatSession yielded, no acquire
    rt.acquire.assert_not_called()


# ── load_band: caller-shape coverage (locks Task-2 equivalence) ──────────

def test_load_band_shape_direct_callback_ocr():
    """ocr shape: progress_callback hits overall bar directly; band=(0.10,0.15)."""
    rt = _emitting_llama_runtime([0.0, 0.5, 1.0])
    svc = ChatService(rt)
    overall = []
    with svc.session(
        model_family="qwen3vl", model_size="2b",
        on_load_progress=lambda p, m: overall.append(p),
        load_band=(0.10, 0.15),
    ):
        pass
    assert overall == [pytest.approx(0.10), pytest.approx(0.125), pytest.approx(0.15)]


def test_load_band_shape_translate_middle_layer():
    """translate shape: translate_progress(percent)->overall=0.05+percent*0.90.
    load_band stage-local (0.0,0.05) must reproduce old translate_progress(p*0.05)."""
    rt = _emitting_llama_runtime([0.0, 1.0])
    svc = ChatService(rt)
    overall = []

    def translate_progress(percent, m):
        overall.append(0.05 + percent * 0.90)

    with svc.session(
        model_family="qwen3", model_size="4b",
        on_load_progress=translate_progress, load_band=(0.0, 0.05),
    ):
        pass
    # raw 0.0 -> percent 0.0 -> overall 0.05 ; raw 1.0 -> percent 0.05 -> overall 0.095
    assert overall == [pytest.approx(0.05), pytest.approx(0.095)]


def test_load_band_shape_stage_progress_thin_lambda():
    """transcribe/subtitle/lyrics shape: stage_progress(name, stage_local, m)."""
    rt = _emitting_llama_runtime([0.0, 1.0])
    svc = ChatService(rt)
    stage_local = []

    def stage_progress(name, x, m):
        assert name == "translate"
        stage_local.append(x)

    with svc.session(
        model_family="qwen3", model_size="4b",
        on_load_progress=lambda p, m: stage_progress("translate", p, m),
        load_band=(0.0, 0.05),
    ):
        pass
    assert stage_local == [pytest.approx(0.0), pytest.approx(0.05)]
