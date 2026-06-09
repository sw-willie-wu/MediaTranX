"""Unit tests for app.services.image.ocr_service."""
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.services.image.ocr_service import (
    ImageOcrService,
    TASK_TYPE_IMAGE_OCR,
    TASK_TYPE_IMAGE_OCR_REMOTE,
)


def _fake_file_service(tmp_path) -> MagicMock:
    fs = MagicMock()
    fs.output_dir = tmp_path / "out"
    fs.output_dir.mkdir()
    fs.upload_dir = tmp_path / "upload"
    fs.upload_dir.mkdir()

    img_path = tmp_path / "in.png"
    img_path.write_bytes(b"\x89PNG\r\n\x1a\n")
    file_info = MagicMock(file_path=img_path, original_filename="in.png")
    fs.require_file.return_value = file_info
    fs.get_file.return_value = file_info

    def _create_output_path(*, original_filename, suffix, ext):
        stem = Path(original_filename).stem
        out_path = fs.output_dir / f"{stem}{suffix}{ext}"
        return f"out_{stem}", out_path
    fs.create_output_path.side_effect = _create_output_path

    def _register_output(*, file_id, file_path, original_filename):
        return MagicMock(filename=Path(file_path).name, file_size=Path(file_path).stat().st_size)
    fs.register_output.side_effect = _register_output
    return fs


def _fake_chat_service(text: str = "extracted"):
    cs = MagicMock()
    @contextmanager
    def _session_cm(*args, **kwargs):
        s = MagicMock()
        s.chat = MagicMock(return_value=text)
        yield s
    cs.session = MagicMock(side_effect=_session_cm)
    return cs


def _fake_model_manager(llama_ready: bool = True):
    mm = MagicMock()
    mm.is_llama_ready.return_value = llama_ready
    @contextmanager
    def _gpu_session():
        yield None
    mm.gpu_session = MagicMock(side_effect=_gpu_session)
    return mm


def _make_svc(tmp_path, *, llama_ready: bool = True, chat_text: str = "hello world\n"):
    fs = _fake_file_service(tmp_path)
    tm = MagicMock()
    mm = _fake_model_manager(llama_ready=llama_ready)
    cs = _fake_chat_service(text=chat_text)
    ls = MagicMock()
    rs = MagicMock()
    svc = ImageOcrService(
        file_service=fs, task_manager=tm, model_manager=mm,
        chat_service=cs, language_service=ls, remote_service=rs,
    )
    return svc, fs, tm, mm, cs, rs


def test_init_registers_both_handlers(tmp_path):
    svc, fs, tm, mm, cs, rs = _make_svc(tmp_path)
    types_registered = [call.args[0] for call in tm.register_handler.call_args_list]
    assert TASK_TYPE_IMAGE_OCR in types_registered
    assert TASK_TYPE_IMAGE_OCR_REMOTE in types_registered
    for call in tm.register_handler.call_args_list:
        assert call.kwargs.get("output_policy") == "results"


def test_get_status_delegates_to_language_service(tmp_path):
    """API: GET /api/image/ocr/status → service.get_status → language_service.get_vlm_status."""
    svc, fs, tm, mm, cs, rs = _make_svc(tmp_path)
    svc._language_service.get_vlm_status.return_value = {"available": True}
    result = svc.get_status(model_family="qwen3vl", size="4b", quantization="Q4_K_M")
    assert result == {"available": True}
    svc._language_service.get_vlm_status.assert_called_once_with(
        model_family="qwen3vl", size="4b", quantization="Q4_K_M",
    )


@pytest.mark.asyncio
async def test_submit_ocr_validates_file_and_submits(tmp_path):
    svc, fs, tm, mm, cs, rs = _make_svc(tmp_path)

    async def _async_submit(*a, **k):
        return "t1"
    tm.submit.side_effect = lambda *a, **k: _async_submit(*a, **k)

    task_id = await svc.submit_ocr(file_id="fid", model_family="qwen3vl", size="4b", format="md")
    assert task_id == "t1"
    fs.require_file.assert_called_once_with("fid")
    args, _ = tm.submit.call_args
    assert args[0] == TASK_TYPE_IMAGE_OCR
    assert args[1]["file_id"] == "fid"
    assert args[1]["model_family"] == "qwen3vl"
    assert args[1]["format"] == "md"


def test_handle_task_raises_when_llama_not_ready(tmp_path):
    svc, *_ = _make_svc(tmp_path, llama_ready=False)
    with pytest.raises(RuntimeError, match="llama-server not installed"):
        svc._handle_task(
            {"file_id": "fid", "model_family": "qwen3vl", "size": "4b", "format": "md"},
            lambda p, m: None,
        )


def test_handle_task_writes_output_and_emits_complete(tmp_path):
    svc, fs, tm, mm, cs, rs = _make_svc(tmp_path, chat_text="recognized text\n")

    events: list[tuple[float, str]] = []
    def on_progress(p, m):
        events.append((p, m))

    with patch("app.pipeline.ocr.recognize_image_local", return_value="recognized text\n"):
        result = svc._handle_task(
            {"file_id": "fid", "model_family": "qwen3vl", "size": "4b", "format": "md"},
            on_progress,
        )

    assert "output_file_id" in result
    assert result["char_count"] == len("recognized text\n")
    written = list(fs.output_dir.glob("in_ocr.md"))
    assert len(written) == 1
    assert written[0].read_text(encoding="utf-8") == "recognized text\n"
    assert events[-1] == (1.0, "task.progress.ocr_complete")
    for _, m in events:
        assert m.startswith("task.progress.")


def test_handle_task_substitutes_placeholder_when_empty(tmp_path):
    svc, fs, *_ = _make_svc(tmp_path)
    with patch("app.pipeline.ocr.recognize_image_local", return_value="   \n"):
        result = svc._handle_task(
            {"file_id": "fid", "model_family": "qwen3vl", "size": "4b", "format": "md"},
            lambda p, m: None,
        )
    written = (fs.output_dir / "in_ocr.md").read_text(encoding="utf-8")
    assert "(No text detected)" in written
    assert result["char_count"] == len("(No text detected)")


@pytest.mark.asyncio
async def test_submit_ocr_remote_passes_provider_params(tmp_path):
    svc, fs, tm, mm, cs, rs = _make_svc(tmp_path)

    async def _async_submit(*a, **k):
        return "tr1"
    tm.submit.side_effect = lambda *a, **k: _async_submit(*a, **k)

    task_id = await svc.submit_ocr_remote(
        file_id="fid", provider="openai", conn_id=7,
        remote_model="gpt-4o", format="txt",
    )
    assert task_id == "tr1"
    args, _ = tm.submit.call_args
    assert args[0] == TASK_TYPE_IMAGE_OCR_REMOTE
    assert args[1]["provider"] == "openai"
    assert args[1]["conn_id"] == 7
    assert args[1]["remote_model"] == "gpt-4o"
    assert args[1]["format"] == "txt"


def test_handle_remote_task_raises_when_provider_unavailable(tmp_path):
    svc, fs, tm, mm, cs, rs = _make_svc(tmp_path)
    rs.get_provider_for_connection.return_value = None
    with pytest.raises(RuntimeError, match="Provider not available"):
        svc._handle_remote_task(
            {"file_id": "fid", "provider": "openai", "conn_id": 1,
             "remote_model": "gpt-4o", "format": "md"},
            lambda p, m: None,
        )


def test_handle_remote_task_writes_output(tmp_path):
    svc, fs, tm, mm, cs, rs = _make_svc(tmp_path)
    prov = MagicMock()
    prov.chat = MagicMock(return_value="remote-text")
    rs.get_provider_for_connection.return_value = prov

    with patch("app.utils.vision_messages.prepare_image_for_remote_vlm",
               return_value=("b64data", "image/png")), \
         patch("app.utils.vision_messages.build_vision_chat_messages",
               return_value=[{"role": "user", "content": "ocr"}]), \
         patch("app.adapters.ai.inference_config.get_remote_inference_config",
               return_value={"max_tokens": 4096, "temperature": 0.1}):
        result = svc._handle_remote_task(
            {"file_id": "fid", "provider": "openai", "conn_id": 1,
             "remote_model": "gpt-4o", "format": "md"},
            lambda p, m: None,
        )
    assert result["char_count"] == len("remote-text")
    written = (fs.output_dir / "in_ocr.md").read_text(encoding="utf-8")
    assert written == "remote-text"


def test_handle_remote_task_uses_streaming_session(tmp_path):
    svc, fs, tm, mm, cs, rs = _make_svc(tmp_path)
    prov = MagicMock()
    prov.chat = MagicMock(return_value="remote-text")
    rs.get_provider_for_connection.return_value = prov
    with patch("app.utils.vision_messages.prepare_image_for_remote_vlm",
               return_value=("b64data", "image/png")), \
         patch("app.utils.vision_messages.build_vision_chat_messages",
               return_value=[{"role": "user", "content": "ocr"}]), \
         patch("app.adapters.ai.inference_config.get_remote_inference_config",
               return_value={"max_tokens": 4096, "temperature": 0.1}):
        svc._handle_remote_task(
            {"file_id": "fid", "provider": "openai", "conn_id": 1,
             "remote_model": "gpt-4o", "format": "md"},
            lambda p, m: None,
        )
    _, kwargs = prov.chat.call_args
    assert kwargs.get("abort_hook") is not None
