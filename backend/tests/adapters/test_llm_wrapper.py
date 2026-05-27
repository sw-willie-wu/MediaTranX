"""Unit tests for LlmWrapper (BaseWrapper subclass holding a LlamaServer)."""
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.adapters.ai.wrapper.base import BaseWrapper
from app.adapters.ai.wrapper.llm import LlmWrapper


def test_is_base_runtime_subclass():
    assert issubclass(LlmWrapper, BaseWrapper)


def test_init_registers_slot():
    w = LlmWrapper(slot="llm")
    assert w.slot == "llm"
    assert not w.is_loaded()


def test_chat_before_load_raises():
    w = LlmWrapper(slot="llm")
    with pytest.raises(RuntimeError, match="not loaded"):
        w.chat(messages=[{"role": "user", "content": "hi"}])


def test_chat_delegates_to_server_and_strips_thinking(monkeypatch):
    """LlmWrapper.chat() calls LlamaServer.post_chat() and strips <think>...</think>."""
    w = LlmWrapper(slot="llm")
    mock_server = MagicMock()
    mock_server.post_chat.return_value = "<think>reasoning here</think>\nFinal answer."
    w._model = mock_server  # simulate post-load state

    out = w.chat(messages=[{"role": "user", "content": "q"}], max_tokens=100)

    mock_server.post_chat.assert_called_once()
    assert out == "Final answer."


def test_complete_delegates_to_server_and_strips_thinking():
    w = LlmWrapper(slot="llm")
    mock_server = MagicMock()
    mock_server.post_completion.return_value = "<think>x</think>hello"
    w._model = mock_server

    out = w.complete(prompt="p", max_tokens=50)

    mock_server.post_completion.assert_called_once()
    assert out == "hello"


def test_strip_thinking_without_tags_is_passthrough():
    assert LlmWrapper._strip_thinking("just text") == "just text"


def test_unload_stops_server():
    w = LlmWrapper(slot="llm")
    mock_server = MagicMock()
    w._model = mock_server
    w._current_config = {"model_id": "x"}

    w.unload()

    mock_server.stop.assert_called_once()
    assert not w.is_loaded()


# ─── Wave E additions ───


class TestLoadImpl:
    def test_load_impl_starts_llamaserver_with_gpu_layers_when_nvidia(self, tmp_path):
        w = LlmWrapper(slot="llm")
        fake_server = MagicMock()
        with patch("app.adapters.ai.wrapper.llm.LlamaServer", return_value=fake_server), \
             patch("app.adapters.device.has_nvidia_gpu", return_value=True):
            result = w._load_impl(tmp_path / "model.gguf", config={"n_ctx": 8192})

        assert result is fake_server
        fake_server.start.assert_called_once()
        kwargs = fake_server.start.call_args.kwargs
        assert kwargs["n_gpu_layers"] == 99
        assert kwargs["n_ctx"] == 8192

    def test_load_impl_uses_cpu_when_no_nvidia(self, tmp_path):
        w = LlmWrapper(slot="llm")
        fake_server = MagicMock()
        with patch("app.adapters.ai.wrapper.llm.LlamaServer", return_value=fake_server), \
             patch("app.adapters.device.has_nvidia_gpu", return_value=False):
            w._load_impl(tmp_path / "model.gguf", config={})

        kwargs = fake_server.start.call_args.kwargs
        assert kwargs["n_gpu_layers"] == 0

    def test_load_impl_passes_mmproj_when_present(self, tmp_path):
        w = LlmWrapper(slot="llm")
        fake_server = MagicMock()
        mmproj = tmp_path / "mmproj.gguf"
        mmproj.write_bytes(b"")
        with patch("app.adapters.ai.wrapper.llm.LlamaServer", return_value=fake_server), \
             patch("app.adapters.device.has_nvidia_gpu", return_value=False):
            w._load_impl(tmp_path / "model.gguf", config={"mmproj_path": mmproj})

        kwargs = fake_server.start.call_args.kwargs
        assert kwargs["mmproj_path"] == mmproj


class TestResolveModelPath:
    def test_unknown_model_id_raises(self):
        w = LlmWrapper(slot="llm")
        with pytest.raises(ValueError, match="Unknown model"):
            w._resolve_model_path("bogus-model", variant="4b:Q4_K_M", manager=MagicMock())

    def test_resolve_gguf_path_parses_size_quant(self):
        """variant='size:quant' → split into size + quant via real registry."""
        from app.adapters.ai.registry import MODELS_REGISTRY, FORMAT_GGUF

        gguf = MODELS_REGISTRY.get(FORMAT_GGUF, {})
        if not gguf:
            pytest.skip("No GGUF families registered")

        known_family = next(iter(gguf))
        specs = gguf[known_family]["specs"]
        size = next(iter(specs))
        variants = specs[size].get("variants", {})
        if not variants:
            pytest.skip(f"No variants for {known_family}/{size}")
        quant = next(iter(variants))

        w = LlmWrapper(slot="llm")
        fake_manager = MagicMock()
        fake_manager.get_model_path.return_value = "/fake/path/model.gguf"

        # mmproj_filename may be present → patch SETTINGS to a tmp path with the file
        variant_spec = variants[quant]
        if "mmproj_filename" in variant_spec:
            pytest.skip("variant has mmproj; covered in separate test")

        model_path, config = w._resolve_model_path(
            known_family, variant=f"{size}:{quant}", manager=fake_manager,
        )
        assert config["size"] == size
        assert config["quantization"] == quant
        assert config["model_id"] == known_family
        assert config["n_ctx"] >= 1


class TestChatStream:
    def test_raises_when_no_model_loaded(self):
        w = LlmWrapper(slot="llm")
        w._model = None
        with pytest.raises(RuntimeError, match="not loaded"):
            list(w.chat_stream(messages=[{"role": "user", "content": "hi"}]))

    def test_forwards_args_to_llama_server(self):
        w = LlmWrapper(slot="llm")
        fake_server = MagicMock()
        fake_server.chat_stream.return_value = iter([{"choices": [{"delta": {"content": "x"}}]}])
        w._model = fake_server
        # Caller would consume the iterator; we just need to verify forwarding.
        result = list(w.chat_stream(
            messages=[{"role": "user", "content": "hi"}],
            tools=[{"name": "t", "description": "d", "parameters": {}}],
            max_tokens=1234,
            temperature=0.42,
        ))
        assert result == [{"choices": [{"delta": {"content": "x"}}]}]
        fake_server.chat_stream.assert_called_once_with(
            messages=[{"role": "user", "content": "hi"}],
            tools=[{"name": "t", "description": "d", "parameters": {}}],
            max_tokens=1234,
            temperature=0.42,
        )

    def test_default_tools_and_temperature(self):
        w = LlmWrapper(slot="llm")
        fake_server = MagicMock()
        fake_server.chat_stream.return_value = iter([])
        w._model = fake_server
        list(w.chat_stream(messages=[{"role": "user", "content": "x"}]))
        # Defaults: tools=None, max_tokens=4096, temperature=0.1
        kwargs = fake_server.chat_stream.call_args.kwargs
        assert kwargs["tools"] is None
        assert kwargs["max_tokens"] == 4096
        assert kwargs["temperature"] == 0.1


class TestKillProcess:
    def test_noop_when_no_model_loaded(self):
        w = LlmWrapper(slot="llm")
        w._model = None
        w.kill_process()  # must not raise

    def test_reroutes_through_server_stop_with_short_timeout(self):
        w = LlmWrapper(slot="llm")
        fake_server = MagicMock()
        w._model = fake_server
        w.kill_process()
        fake_server.stop.assert_called_once_with(timeout=2.0)

    def test_swallows_stop_exception(self):
        w = LlmWrapper(slot="llm")
        fake_server = MagicMock()
        fake_server.stop.side_effect = OSError("zombie")
        w._model = fake_server
        w.kill_process()  # must not raise


class TestLoadImplStopsPrior:
    def test_load_impl_stops_existing_server_before_reload(self, tmp_path):
        w = LlmWrapper(slot="llm")
        old_server = MagicMock()
        w._model = old_server
        new_server = MagicMock()
        with patch("app.adapters.ai.wrapper.llm.LlamaServer",
                   return_value=new_server), \
             patch("app.adapters.device.has_nvidia_gpu", return_value=False):
            result = w._load_impl(tmp_path / "m.gguf", config={})
        old_server.stop.assert_called_once()
        assert result is new_server
