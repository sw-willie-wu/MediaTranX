"""Unit tests for app.pipeline.ocr — VLM single-image + PDF-page OCR orchestration."""
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.pipeline import ocr as ocr_pipeline


_FAKE_CONFIG = {
    "n_ctx": 4096,
    "temperature": 0.1,
    "top_k": 40,
    "top_p": 0.9,
    "prompt_builder": "default",
    "thinking": False,
    "max_tokens_strategy": "fixed",
    "max_tokens": 1024,
}


@contextmanager
def _noop_fake_progress(*args, **kwargs):
    yield


def _fake_builder_result():
    return {"mode": "chat", "messages": [{"role": "user", "content": "ocr-this"}]}


def _make_session(text: str = "extracted-text") -> MagicMock:
    s = MagicMock()
    s.chat = MagicMock(return_value=text)
    return s


def test_recognize_image_local_strips_quantization_from_variant():
    """variant 'Q4_K_M' suffix must be stripped before inference_config lookup."""
    session = _make_session()
    with patch("app.adapters.ai.inference_config.get_inference_config", return_value=_FAKE_CONFIG) as gic, \
         patch("app.utils.prompts.get_prompt_builder", return_value=lambda *a, **k: _fake_builder_result()), \
         patch("app.utils.inference.fake_progress", _noop_fake_progress), \
         patch("app.utils.inference.calc_max_tokens", return_value=1024):
        ocr_pipeline.recognize_image_local(
            image_path="/img.png", model_family="qwen3vl",
            variant="4b:Q4_K_M", fmt="md", session=session,
        )
    args, _kwargs = gic.call_args
    assert args[0] == "qwen3vl"
    assert args[1] == "4b"
    assert args[2] == "ocr"


def test_recognize_image_local_calls_session_chat():
    """recognize_image_local must call session.chat with builder-produced messages."""
    session = _make_session(text="hello\n")
    with patch("app.adapters.ai.inference_config.get_inference_config", return_value=_FAKE_CONFIG), \
         patch("app.utils.prompts.get_prompt_builder", return_value=lambda *a, **k: _fake_builder_result()), \
         patch("app.utils.inference.fake_progress", _noop_fake_progress), \
         patch("app.utils.inference.calc_max_tokens", return_value=1024):
        result = ocr_pipeline.recognize_image_local(
            image_path="/img.png", model_family="qwen3vl",
            variant="4b", fmt="md", session=session,
        )
    assert result == "hello\n"
    session.chat.assert_called_once()
    kwargs = session.chat.call_args.kwargs
    assert kwargs["messages"] == [{"role": "user", "content": "ocr-this"}]
    assert kwargs["temperature"] == 0.1
    assert kwargs["max_tokens"] == 1024


def test_recognize_image_local_does_not_acquire():
    """Per docstring: function must NOT acquire — caller owns session lifecycle."""
    session = _make_session()
    with patch("app.adapters.ai.inference_config.get_inference_config", return_value=_FAKE_CONFIG), \
         patch("app.utils.prompts.get_prompt_builder", return_value=lambda *a, **k: _fake_builder_result()), \
         patch("app.utils.inference.fake_progress", _noop_fake_progress), \
         patch("app.utils.inference.calc_max_tokens", return_value=1024):
        ocr_pipeline.recognize_image_local(
            image_path="/img.png", model_family="gemma4",
            variant="4b", fmt="txt", session=session,
        )
    assert not session.acquire.called


def test_ocr_pdf_pages_calls_recognize_per_page(tmp_path):
    """ocr_pdf_pages must render each PDF page once and call recognize_fn(path)."""
    pdf_path = tmp_path / "doc.pdf"
    fake_page = MagicMock()
    fake_bitmap = MagicMock()
    fake_pil = MagicMock()
    fake_bitmap.to_pil = MagicMock(return_value=fake_pil)
    fake_page.render = MagicMock(return_value=fake_bitmap)
    fake_pdf = MagicMock()
    fake_pdf.__len__ = MagicMock(return_value=3)
    fake_pdf.__getitem__ = MagicMock(return_value=fake_page)
    fake_pdf.close = MagicMock()

    recognized: list[str] = []
    def _recognize(img_path: str) -> str:
        recognized.append(img_path)
        return f"page-{len(recognized)}\n"

    with patch("pypdfium2.PdfDocument", return_value=fake_pdf):
        results = ocr_pipeline.ocr_pdf_pages(pdf_path, _recognize)

    assert len(results) == 3
    assert results == ["page-1", "page-2", "page-3"]
    assert len(recognized) == 3
    assert fake_page.render.call_count == 3
    fake_pdf.close.assert_called_once()


def test_ocr_pdf_pages_emits_per_page_progress(tmp_path):
    """Progress callback fires (i/total, 'task.progress.doc_ocr_page|i+1|total') per page."""
    pdf_path = tmp_path / "doc.pdf"
    fake_page = MagicMock()
    fake_page.render = MagicMock(return_value=MagicMock(to_pil=MagicMock(return_value=MagicMock())))
    fake_pdf = MagicMock()
    fake_pdf.__len__ = MagicMock(return_value=2)
    fake_pdf.__getitem__ = MagicMock(return_value=fake_page)
    fake_pdf.close = MagicMock()

    events: list[tuple[float, str]] = []
    def on_progress(p, m): events.append((p, m))

    with patch("pypdfium2.PdfDocument", return_value=fake_pdf):
        ocr_pipeline.ocr_pdf_pages(pdf_path, lambda img: "x", on_progress=on_progress)

    assert events == [
        (0.0, "task.progress.doc_ocr_page|1|2"),
        (0.5, "task.progress.doc_ocr_page|2|2"),
    ]
