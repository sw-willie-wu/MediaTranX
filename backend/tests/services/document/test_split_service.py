"""Unit tests for app.services.document.split_service."""
import shutil
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app.services.document.split_service import (
    DocumentSplitService,
    TASK_TYPE_DOCUMENT_SPLIT,
    _parse_page_ranges,
)


# --- _parse_page_ranges ---

def test_parse_page_ranges_single_pages():
    assert _parse_page_ranges("1,3,5", total=10) == [0, 2, 4]


def test_parse_page_ranges_dash_range():
    assert _parse_page_ranges("1-3", total=10) == [0, 1, 2]


def test_parse_page_ranges_mixed():
    assert _parse_page_ranges("1-3,5,7-9", total=10) == [0, 1, 2, 4, 6, 7, 8]


def test_parse_page_ranges_clamps_to_total():
    # 5-100 with total=3 → lo=5, hi=min(3,100)=3 → range(4,3) = []
    assert _parse_page_ranges("5-100", total=3) == []


def test_parse_page_ranges_with_spaces():
    assert _parse_page_ranges("1 - 3 , 5", total=10) == [0, 1, 2, 4]


def test_parse_page_ranges_empty_part_ignored():
    assert _parse_page_ranges("1,,3", total=10) == [0, 2]


# --- service ---

def _make_svc(tmp_path, *, src_path: Path):
    fs = MagicMock()
    fs.output_dir = tmp_path / "out"; fs.output_dir.mkdir()
    fi = MagicMock(file_path=src_path, original_filename="doc.pdf")
    fs.require_file.return_value = fi

    def _register_output(*, file_id, file_path, original_filename):
        return MagicMock(filename=Path(file_path).name, file_size=Path(file_path).stat().st_size)
    fs.register_output.side_effect = _register_output

    tm = MagicMock()
    svc = DocumentSplitService(file_service=fs, task_manager=tm)
    return svc, fs, tm


def test_init_registers_handler(tmp_path, tiny_pdf_path):
    svc, fs, tm = _make_svc(tmp_path, src_path=tiny_pdf_path)
    tm.register_handler.assert_called_once()
    args, kwargs = tm.register_handler.call_args
    assert args[0] == TASK_TYPE_DOCUMENT_SPLIT
    assert kwargs.get("output_policy") == "results"


@pytest.mark.asyncio
async def test_submit_passes_pages(tmp_path, tiny_pdf_path):
    svc, fs, tm = _make_svc(tmp_path, src_path=tiny_pdf_path)
    async def _submit(*a, **k): return "tsp"
    tm.submit.side_effect = lambda *a, **k: _submit(*a, **k)
    task_id = await svc.submit(file_id="fid", pages="1-2")
    assert task_id == "tsp"
    args, _ = tm.submit.call_args
    assert args[1]["pages"] == "1-2"


def test_execute_extracts_specified_pages(tmp_path, tiny_pdf_path):
    """tiny.pdf has 3 blank pages — extract pages 1-2 → 2-page output."""
    fixture_copy = tmp_path / "doc.pdf"
    shutil.copy(tiny_pdf_path, fixture_copy)
    svc, fs, tm = _make_svc(tmp_path, src_path=fixture_copy)
    result = svc._execute({"file_id": "fid", "pages": "1-2"}, lambda p, m: None)
    assert result["page_count"] == 2
    assert result["total_pages"] == 3
    assert "p1-2" in result["output_filename"]


def test_execute_default_extracts_all_pages_when_empty(tmp_path, tiny_pdf_path):
    fixture_copy = tmp_path / "doc.pdf"
    shutil.copy(tiny_pdf_path, fixture_copy)
    svc, fs, tm = _make_svc(tmp_path, src_path=fixture_copy)
    result = svc._execute({"file_id": "fid", "pages": ""}, lambda p, m: None)
    assert result["page_count"] == 3


def test_execute_raises_on_invalid_range(tmp_path, tiny_pdf_path):
    fixture_copy = tmp_path / "doc.pdf"
    shutil.copy(tiny_pdf_path, fixture_copy)
    svc, fs, tm = _make_svc(tmp_path, src_path=fixture_copy)
    with pytest.raises(ValueError, match="Invalid page range"):
        svc._execute({"file_id": "fid", "pages": "99-100"}, lambda p, m: None)


def test_execute_emits_split_complete(tmp_path, tiny_pdf_path):
    fixture_copy = tmp_path / "doc.pdf"
    shutil.copy(tiny_pdf_path, fixture_copy)
    svc, fs, tm = _make_svc(tmp_path, src_path=fixture_copy)
    events = []
    def cb(p, m): events.append((p, m))
    svc._execute({"file_id": "fid", "pages": "1"}, cb)
    assert events[-1] == (1.0, "task.progress.split_complete")
    for _, m in events:
        assert m.startswith("task.progress.")
