"""Tests for extract_changelog.py (run from repo root):
uv run --project backend --extra dev python -m pytest scripts/test_extract_changelog.py -v
"""
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from extract_changelog import extract_section

SCRIPT = Path(__file__).parent / "extract_changelog.py"

SAMPLE = """# Changelog

## [1.6.0] - 2026-07-10
### 新增
- 意見回報

## [1.5.2] - 2026-06-13
- 修正若干問題
"""


def test_middle_section_excludes_heading_and_next():
    assert extract_section(SAMPLE, "1.6.0") == "### 新增\n- 意見回報"


def test_last_section_reaches_eof():
    assert extract_section(SAMPLE, "1.5.2") == "- 修正若干問題"


def test_missing_version_returns_none():
    assert extract_section(SAMPLE, "9.9.9") is None


def test_bare_heading_without_date():
    assert extract_section("## [2.0.0]\nx\n", "2.0.0") == "x"


def test_dots_are_literal_not_regex():
    text = "## [1x6x0]\nwrong\n\n## [1.6.0]\nright\n"
    assert extract_section(text, "1.6.0") == "right"


def test_empty_section_returns_empty_string():
    assert extract_section("## [1.0.0]\n\n## [0.9.0]\nx\n", "1.0.0") == ""


def _run(args, changelog: Path):
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args, "--changelog", str(changelog)],
        capture_output=True, text=True, encoding="utf-8",
    )


def test_cli_out_writes_body(tmp_path):
    cl = tmp_path / "CHANGELOG.md"
    cl.write_text(SAMPLE, encoding="utf-8")
    out = tmp_path / "notes.md"
    r = _run(["1.6.0", "--out", str(out)], cl)
    assert r.returncode == 0
    assert out.read_text(encoding="utf-8") == "### 新增\n- 意見回報\n"


def test_cli_missing_section_exits_1(tmp_path):
    cl = tmp_path / "CHANGELOG.md"
    cl.write_text(SAMPLE, encoding="utf-8")
    r = _run(["9.9.9"], cl)
    assert r.returncode == 1
    assert "no `## [9.9.9]`" in r.stderr


def test_cli_empty_section_exits_1(tmp_path):
    cl = tmp_path / "CHANGELOG.md"
    cl.write_text("## [1.0.0]\n\n## [0.9.0]\nx\n", encoding="utf-8")
    r = _run(["1.0.0"], cl)
    assert r.returncode == 1
    assert "empty" in r.stderr


def test_check_rejects_bom(tmp_path):
    cl = tmp_path / "CHANGELOG.md"
    cl.write_bytes(b"\xef\xbb\xbf" + SAMPLE.encode("utf-8"))
    r = _run(["1.6.0", "--check"], cl)
    assert r.returncode == 1
    assert "BOM" in r.stderr


def test_check_rejects_date_placeholder(tmp_path):
    cl = tmp_path / "CHANGELOG.md"
    cl.write_text("## [1.6.0] - 2026-07-XX\n- 內容\n", encoding="utf-8")
    r = _run(["1.6.0", "--check"], cl)
    assert r.returncode == 1
    assert "placeholder" in r.stderr


def test_check_passes_valid(tmp_path):
    cl = tmp_path / "CHANGELOG.md"
    cl.write_text(SAMPLE, encoding="utf-8")
    r = _run(["1.6.0", "--check"], cl)
    assert r.returncode == 0
