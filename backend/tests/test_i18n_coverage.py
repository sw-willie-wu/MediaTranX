"""Tests for i18n coverage — verify all task.progress.* keys used in backend exist in locale files."""
import re
from pathlib import Path

import pytest


def _collect_backend_keys() -> set[str]:
    """Scan all backend .py files for task.progress.* keys used in progress callbacks."""
    backend_dir = Path(__file__).parent.parent / "app"
    keys = set()
    pattern = re.compile(r'task\.progress\.([a-z0-9_]+)')
    for py_file in backend_dir.rglob("*.py"):
        content = py_file.read_text(encoding="utf-8", errors="ignore")
        for match in pattern.finditer(content):
            keys.add(f"task.progress.{match.group(1)}")
    return keys


def _parse_locale_keys(locale_path: Path) -> set[str]:
    """Extract task.progress.* keys from a TypeScript locale file."""
    content = locale_path.read_text(encoding="utf-8")

    # Find the task.progress block and extract key names
    keys = set()
    in_progress_block = False
    for line in content.splitlines():
        stripped = line.strip()
        if "progress:" in stripped and "{" in stripped:
            in_progress_block = True
            continue
        if in_progress_block:
            if stripped.startswith("}"):
                in_progress_block = False
                continue
            # Match key: 'value', or key: "value",
            m = re.match(r"(\w+)\s*:", stripped)
            if m and not stripped.startswith("//"):
                keys.add(f"task.progress.{m.group(1)}")
    return keys


class TestI18nCoverage:
    @pytest.fixture
    def backend_keys(self):
        return _collect_backend_keys()

    @pytest.fixture
    def en_keys(self):
        en_path = Path(__file__).parent.parent.parent / "frontend" / "src" / "i18n" / "locales" / "en.ts"
        if not en_path.exists():
            pytest.skip("en.ts not found")
        return _parse_locale_keys(en_path)

    @pytest.fixture
    def zh_keys(self):
        zh_path = Path(__file__).parent.parent.parent / "frontend" / "src" / "i18n" / "locales" / "zh-TW.ts"
        if not zh_path.exists():
            pytest.skip("zh-TW.ts not found")
        return _parse_locale_keys(zh_path)

    def test_all_backend_keys_in_en(self, backend_keys, en_keys):
        missing = backend_keys - en_keys
        assert not missing, f"Backend uses these keys but en.ts is missing them:\n{sorted(missing)}"

    def test_all_backend_keys_in_zh(self, backend_keys, zh_keys):
        missing = backend_keys - zh_keys
        assert not missing, f"Backend uses these keys but zh-TW.ts is missing them:\n{sorted(missing)}"

    def test_en_and_zh_have_same_keys(self, en_keys, zh_keys):
        en_only = en_keys - zh_keys
        zh_only = zh_keys - en_keys
        assert not en_only, f"Keys in en.ts but not zh-TW.ts:\n{sorted(en_only)}"
        assert not zh_only, f"Keys in zh-TW.ts but not en.ts:\n{sorted(zh_only)}"

    def test_backend_uses_some_keys(self, backend_keys):
        """Sanity check: backend should use at least some progress keys."""
        assert len(backend_keys) > 20, f"Only found {len(backend_keys)} keys, expected more"
