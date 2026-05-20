"""Unit tests for app.services.document.pdf_convert_service."""
import shutil
import zipfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.services.document.pdf_convert_service import (
    DocumentPdfConvertService,
    TASK_TYPE_DOCUMENT_PDF_CONVERT,
)


def _make_svc(tmp_path, *, src_name="in.pdf", src_path: Path = None):
    fs = MagicMock()
    fs.output_dir = tmp_path / "out"; fs.output_dir.mkdir()
    src = src_path if src_path else tmp_path / src_name
    if src_path is None:
        src.write_bytes(b"\x00")
    fi = MagicMock(file_path=src, original_filename=src_name)
    fs.require_file.return_value = fi

    def _register_output(*, file_id, file_path, original_filename):
        return MagicMock(filename=Path(file_path).name, file_size=Path(file_path).stat().st_size)
    fs.register_output.side_effect = _register_output

    tm = MagicMock()
    svc = DocumentPdfConvertService(file_service=fs, task_manager=tm)
    return svc, fs, tm


def test_init_registers_handler(tmp_path):
    svc, fs, tm = _make_svc(tmp_path)
    tm.register_handler.assert_called_once()
    args, kwargs = tm.register_handler.call_args
    assert args[0] == TASK_TYPE_DOCUMENT_PDF_CONVERT
    assert kwargs.get("output_policy") == "results"


@pytest.mark.asyncio
async def test_submit_passes_params(tmp_path):
    svc, fs, tm = _make_svc(tmp_path)
    async def _submit(*a, **k): return "tp"
    tm.submit.side_effect = lambda *a, **k: _submit(*a, **k)
    task_id = await svc.submit(file_id="fid", output_format="md")
    assert task_id == "tp"
    args, _ = tm.submit.call_args
    assert args[1]["output_format"] == "md"


def test_execute_pdf_to_txt_extracts_real_pages(tmp_path, tiny_pdf_path):
    """Use the tiny.pdf fixture (3 blank pages) — pypdf.PdfReader runs for real."""
    fixture_copy = tmp_path / "doc.pdf"
    shutil.copy(tiny_pdf_path, fixture_copy)
    svc, fs, tm = _make_svc(tmp_path, src_name="doc.pdf", src_path=fixture_copy)
    result = svc._execute({"file_id": "fid", "output_format": "txt"}, lambda p, m: None)
    assert "output_file_id" in result
    out = fs.output_dir / "doc_converted.txt"
    assert out.exists()


def test_execute_pdf_to_images_emits_zip(tmp_path, tiny_pdf_path):
    """PDF → images branch writes a real ZIP of PNGs via pypdfium2."""
    fixture_copy = tmp_path / "doc.pdf"
    shutil.copy(tiny_pdf_path, fixture_copy)
    svc, fs, tm = _make_svc(tmp_path, src_name="doc.pdf", src_path=fixture_copy)
    svc._execute({"file_id": "fid", "output_format": "images"}, lambda p, m: None)
    out = fs.output_dir / "doc_converted.zip"
    assert out.exists()
    with zipfile.ZipFile(out) as zf:
        names = zf.namelist()
    assert len(names) == 3
    assert all(n.startswith("page_") and n.endswith(".png") for n in names)


def test_execute_images_format_rejects_non_pdf(tmp_path):
    svc, fs, tm = _make_svc(tmp_path, src_name="doc.docx")
    with pytest.raises(ValueError, match="Only PDF format supports conversion to images"):
        svc._execute({"file_id": "fid", "output_format": "images"}, lambda p, m: None)


def test_execute_docx_extracts_paragraphs(tmp_path):
    svc, fs, tm = _make_svc(tmp_path, src_name="doc.docx")
    fake_doc = MagicMock()
    fake_doc.paragraphs = [MagicMock(text="line one"), MagicMock(text="line two"), MagicMock(text="  ")]
    with patch("docx.Document", return_value=fake_doc):
        svc._execute({"file_id": "fid", "output_format": "txt"}, lambda p, m: None)
    out = fs.output_dir / "doc_converted.txt"
    text = out.read_text(encoding="utf-8")
    assert "line one" in text
    assert "line two" in text


def test_execute_plain_text_copies_content(tmp_path):
    svc, fs, tm = _make_svc(tmp_path, src_name="notes.md")
    fs.require_file.return_value.file_path.write_text("# Hello\nWorld", encoding="utf-8")
    svc._execute({"file_id": "fid", "output_format": "txt"}, lambda p, m: None)
    out = fs.output_dir / "notes_converted.txt"
    assert out.read_text(encoding="utf-8") == "# Hello\nWorld"


def test_execute_emits_progress_keys(tmp_path, tiny_pdf_path):
    import re
    progress_re = re.compile(r"^task\.progress\.[a-z_]+(\|.+)*$")
    fixture_copy = tmp_path / "doc.pdf"
    shutil.copy(tiny_pdf_path, fixture_copy)
    svc, fs, tm = _make_svc(tmp_path, src_name="doc.pdf", src_path=fixture_copy)
    events = []
    def cb(p, m): events.append((p, m))
    svc._execute({"file_id": "fid", "output_format": "txt"}, cb)
    bad = [m for _, m in events if not progress_re.match(m)]
    assert not bad, f"Non-i18n progress messages: {bad}"
    assert events[-1] == (1.0, "task.progress.convert_complete")
