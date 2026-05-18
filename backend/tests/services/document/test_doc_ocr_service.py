"""Unit tests for app.services.document.doc_ocr_service."""
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.services.document.doc_ocr_service import (
    DocumentOcrService,
    TASK_TYPE_DOCUMENT_OCR,
    TASK_TYPE_DOCUMENT_OCR_REMOTE,
)


def _fake_file_service_with(tmp_path, src_name: str) -> tuple[MagicMock, Path]:
    fs = MagicMock()
    fs.output_dir = tmp_path / "out"
    fs.output_dir.mkdir()
    fs.upload_dir = tmp_path / "upload"
    fs.upload_dir.mkdir()
    src_path = tmp_path / src_name
    src_path.write_bytes(b"\x00")
    fi = MagicMock(file_path=src_path, original_filename=src_name)
    fs.require_file.return_value = fi

    def _create_output_path(*, original_filename, suffix, ext):
        stem = Path(original_filename).stem
        out_path = fs.output_dir / f"{stem}{suffix}{ext}"
        return f"out_{stem}", out_path
    fs.create_output_path.side_effect = _create_output_path

    def _register_output(*, file_id, file_path, original_filename):
        return MagicMock(filename=Path(file_path).name, file_size=Path(file_path).stat().st_size)
    fs.register_output.side_effect = _register_output
    return fs, src_path


def _fake_chat_service(text="recognized"):
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


def _make_svc(tmp_path, src_name="in.png", *, llama_ready=True):
    fs, src_path = _fake_file_service_with(tmp_path, src_name)
    tm = MagicMock()
    mm = _fake_model_manager(llama_ready=llama_ready)
    cs = _fake_chat_service()
    ls = MagicMock()
    rs = MagicMock()
    svc = DocumentOcrService(
        file_service=fs, task_manager=tm, model_manager=mm,
        chat_service=cs, language_service=ls, remote_service=rs,
    )
    return svc, fs, tm, mm, cs, rs, src_path


def test_init_registers_both_handlers(tmp_path):
    svc, *_ = _make_svc(tmp_path)
    types_registered = [call.args[0] for call in svc._task_manager.register_handler.call_args_list]
    assert TASK_TYPE_DOCUMENT_OCR in types_registered
    assert TASK_TYPE_DOCUMENT_OCR_REMOTE in types_registered


def test_handle_task_image_path_writes_output(tmp_path):
    svc, fs, *_rest = _make_svc(tmp_path, "in.png")
    with patch("app.pipeline.ocr.recognize_image_local", return_value="img-text"):
        result = svc._handle_task(
            {"file_id": "fid", "model_family": "qwen3vl", "size": "4b",
             "quantization": None, "format": "md"},
            lambda p, m: None,
        )
    assert result["char_count"] == len("img-text")
    out_file = fs.output_dir / "in_ocr.md"
    assert out_file.read_text(encoding="utf-8") == "img-text"


def test_handle_task_pdf_path_joins_pages_with_md_headers(tmp_path):
    svc, fs, *_rest = _make_svc(tmp_path, "in.pdf")
    with patch("app.pipeline.ocr.recognize_image_local", side_effect=["pg1", "pg2"]), \
         patch("app.pipeline.ocr.ocr_pdf_pages",
               side_effect=lambda pdf_path, recognize_fn, on_progress=None: [recognize_fn(f"img-{i}") for i in range(2)]):
        svc._handle_task(
            {"file_id": "fid", "model_family": "qwen3vl", "size": "4b",
             "quantization": None, "format": "md"},
            lambda p, m: None,
        )
    written = (fs.output_dir / "in_ocr.md").read_text(encoding="utf-8")
    assert "## Page 1" in written
    assert "## Page 2" in written
    assert "pg1" in written and "pg2" in written
    assert "\n\n---\n\n" in written


def test_handle_task_pdf_txt_format_joins_with_blank_line(tmp_path):
    svc, fs, *_rest = _make_svc(tmp_path, "in.pdf")
    with patch("app.pipeline.ocr.recognize_image_local", side_effect=["pg1", "pg2"]), \
         patch("app.pipeline.ocr.ocr_pdf_pages",
               side_effect=lambda pdf_path, recognize_fn, on_progress=None: [recognize_fn(f"img-{i}") for i in range(2)]):
        svc._handle_task(
            {"file_id": "fid", "model_family": "qwen3vl", "size": "4b",
             "quantization": None, "format": "txt"},
            lambda p, m: None,
        )
    written = (fs.output_dir / "in_ocr.txt").read_text(encoding="utf-8")
    assert written == "pg1\n\npg2"


def test_handle_task_rejects_unsupported_format(tmp_path):
    svc, *_ = _make_svc(tmp_path, "in.docx")
    with pytest.raises(ValueError, match="Unsupported file format"):
        svc._handle_task(
            {"file_id": "fid", "model_family": "qwen3vl", "size": "4b",
             "quantization": None, "format": "md"},
            lambda p, m: None,
        )


def test_handle_task_substitutes_placeholder_for_empty(tmp_path):
    svc, fs, *_rest = _make_svc(tmp_path, "in.png")
    with patch("app.pipeline.ocr.recognize_image_local", return_value="   "):
        svc._handle_task(
            {"file_id": "fid", "model_family": "qwen3vl", "size": "4b",
             "quantization": None, "format": "md"},
            lambda p, m: None,
        )
    written = (fs.output_dir / "in_ocr.md").read_text(encoding="utf-8")
    assert "(No text detected)" in written


def test_handle_task_raises_when_llama_not_ready(tmp_path):
    svc, *_ = _make_svc(tmp_path, "in.png", llama_ready=False)
    with pytest.raises(RuntimeError, match="llama-server not installed"):
        svc._handle_task(
            {"file_id": "fid", "model_family": "qwen3vl", "size": "4b",
             "quantization": None, "format": "md"},
            lambda p, m: None,
        )


def test_handle_remote_task_provider_unavailable(tmp_path):
    svc, fs, tm, mm, cs, rs, _src = _make_svc(tmp_path, "in.png")
    rs.get_provider_for_connection.return_value = None
    with pytest.raises(RuntimeError, match="Provider not available"):
        svc._handle_remote_task(
            {"file_id": "fid", "provider": "openai", "conn_id": 1,
             "remote_model": "gpt-4o", "format": "md"},
            lambda p, m: None,
        )


def test_handle_remote_task_image_writes_output(tmp_path):
    svc, fs, tm, mm, cs, rs, _src = _make_svc(tmp_path, "in.png")
    prov = MagicMock()
    prov.chat = MagicMock(return_value="remote-img-text")
    rs.get_provider_for_connection.return_value = prov

    with patch("app.utils.vision_messages.prepare_image_for_remote_vlm",
               return_value=("b64", "image/png")), \
         patch("app.utils.vision_messages.build_vision_chat_messages",
               return_value=[{"role": "user", "content": "x"}]), \
         patch("app.adapters.ai.inference_config.get_remote_inference_config",
               return_value={"max_tokens": 4096, "temperature": 0.1}):
        result = svc._handle_remote_task(
            {"file_id": "fid", "provider": "openai", "conn_id": 1,
             "remote_model": "gpt-4o", "format": "md"},
            lambda p, m: None,
        )
    assert result["char_count"] == len("remote-img-text")
    assert (fs.output_dir / "in_ocr.md").read_text(encoding="utf-8") == "remote-img-text"


def test_handle_remote_task_pdf_joins_pages(tmp_path):
    svc, fs, tm, mm, cs, rs, _src = _make_svc(tmp_path, "in.pdf")
    prov = MagicMock()
    rs.get_provider_for_connection.return_value = prov

    with patch.object(svc, "_recognize_remote", side_effect=["pdf-pg1", "pdf-pg2"]), \
         patch("app.pipeline.ocr.ocr_pdf_pages",
               side_effect=lambda pdf_path, recognize_fn, on_progress=None: [recognize_fn(f"img-{i}") for i in range(2)]):
        svc._handle_remote_task(
            {"file_id": "fid", "provider": "openai", "conn_id": 1,
             "remote_model": "gpt-4o", "format": "md"},
            lambda p, m: None,
        )
    written = (fs.output_dir / "in_ocr.md").read_text(encoding="utf-8")
    assert "pdf-pg1" in written and "pdf-pg2" in written
    assert "\n\n---\n\n" in written


def test_handle_remote_task_rejects_unsupported_format(tmp_path):
    svc, fs, tm, mm, cs, rs, _src = _make_svc(tmp_path, "in.docx")
    prov = MagicMock()
    rs.get_provider_for_connection.return_value = prov
    with pytest.raises(ValueError, match="Unsupported file format"):
        svc._handle_remote_task(
            {"file_id": "fid", "provider": "openai", "conn_id": 1,
             "remote_model": "gpt-4o", "format": "md"},
            lambda p, m: None,
        )
