"""diagnostics 低階工具：遮罩、UTF-8 邊界截斷、seek-tail。"""
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.services.feedback.config import (
    CORE_ERROR_CAP_BYTES,
    EMPTY_SECTION,
    LOG_TAIL_CAP_BYTES,
    SECTION_ASSEMBLY_CHAR_CAP,
)
from app.services.feedback.diagnostics import (
    DiagnosticsSections,
    build_diagnostics,
    read_tail_bytes,
    redact_usernames,
    truncate_utf8_tail,
)


class TestRedactUsernames:
    def test_backslash_path(self):
        assert redact_usernames(r"C:\Users\willie\Repos\x.mp4") == r"C:\Users\***\Repos\x.mp4"

    def test_forward_slash_path(self):
        assert redact_usernames("C:/Users/willie/x") == "C:/Users/***/x"

    def test_line_end_no_trailing_sep(self):
        # 路徑在行尾、沒有尾隨分隔符也要遮
        assert redact_usernames(r"log at C:\Users\willie") == r"log at C:\Users\***"

    def test_case_insensitive(self):
        assert redact_usernames(r"c:\users\Willie\x") == r"c:\users\***\x"

    def test_unc_variant(self):
        assert redact_usernames(r"\\myhost\Users\willie\share") == r"\\myhost\Users\***\share"

    def test_boundary_quote_semicolon(self):
        assert redact_usernames('path="C:\\Users\\willie";next') == 'path="C:\\Users\\***";next'

    def test_idempotent(self):
        once = redact_usernames(r"C:\Users\willie\a and C:\Users\willie")
        assert redact_usernames(once) == once

    def test_media_filename_not_redacted(self):
        # 媒體檔名不遮（診斷價值）
        out = redact_usernames(r"C:\Users\willie\Videos\my_secret_video.mp4")
        assert "my_secret_video.mp4" in out


class TestTruncateUtf8Tail:
    def test_no_truncation_needed(self):
        assert truncate_utf8_tail("abc", 10) == "abc"

    def test_keeps_tail(self):
        assert truncate_utf8_tail("0123456789", 4) == "6789"

    def test_cjk_boundary(self):
        # 「中」UTF-8 3 bytes；cap 落在字元中間必須往後退到完整字元
        text = "a中b中c"           # bytes: a(1) 中(3) b(1) 中(3) c(1) = 9
        out = truncate_utf8_tail(text, 4)  # 尾 4 bytes = 中(3)+c(1) 恰好邊界
        assert out == "中c"
        out2 = truncate_utf8_tail(text, 6)  # 尾 6 bytes 切進第二個「中」中間 → 退掉殘缺 bytes
        assert out2 == "b中c"               # 剩 b(1)+中(3)+c(1)=5 bytes
        assert len(out2.encode("utf-8")) <= 6

    def test_result_always_within_cap(self):
        text = "中" * 100
        for cap in range(1, 12):
            assert len(truncate_utf8_tail(text, cap).encode("utf-8")) <= cap


class TestReadTailBytes:
    def test_missing_file_returns_none(self, tmp_path: Path):
        assert read_tail_bytes(tmp_path / "nope.log", 100) is None

    def test_small_file_full_content(self, tmp_path: Path):
        p = tmp_path / "a.log"
        p.write_bytes(b"hello")
        assert read_tail_bytes(p, 100) == b"hello"

    def test_large_file_seeks_tail(self, tmp_path: Path):
        p = tmp_path / "big.log"
        p.write_bytes(b"x" * 10_000 + b"TAIL")
        out = read_tail_bytes(p, 8)
        assert out == b"xxxxTAIL"
        assert len(out) == 8


def _mk_settings(tmp_path):
    # 只需要 path.log；仿 conftest settings 但把 log 指到 tmp
    return SimpleNamespace(path=SimpleNamespace(log=tmp_path / "logs"))


def _mk_task_manager(task=None):
    tm = MagicMock()
    tm.get_task.return_value = task
    return tm


class TestBuildDiagnostics:
    def test_missing_logs_yield_empty_marker(self, tmp_path):
        d = build_diagnostics(settings=_mk_settings(tmp_path), task_manager=_mk_task_manager(), task_id=None)
        assert isinstance(d, DiagnosticsSections)
        assert EMPTY_SECTION in d.log_tail          # 兩檔皆缺 → 標示 (無)
        assert d.task_context == EMPTY_SECTION      # 無 task_id

    def test_env_summary_is_redacted_and_capped(self, tmp_path):
        big = (r"C:\Users\willie\x " * 2) + "y" * 20_000
        with patch("app.services.feedback.diagnostics.collect_env_summary", return_value=big):
            d = build_diagnostics(settings=_mk_settings(tmp_path), task_manager=_mk_task_manager(), task_id=None)
        assert "willie" not in d.env_summary
        assert len(d.env_summary) <= SECTION_ASSEMBLY_CHAR_CAP   # 不變量 (d)

    def test_task_context_from_task_manager(self, tmp_path):
        task = SimpleNamespace(
            task_type="image.compress", error="boom at C:\\Users\\willie\\a.png",
            error_code="ffmpeg_error",
            created_at=__import__("datetime").datetime(2026, 7, 4, 12, 0, 0),
        )
        d = build_diagnostics(settings=_mk_settings(tmp_path), task_manager=_mk_task_manager(task), task_id="t-1")
        assert "image.compress" in d.task_context
        assert "ffmpeg_error" in d.task_context
        assert "willie" not in d.task_context       # 任務脈絡也要遮罩

    def test_task_context_falls_back_to_history_dao(self, tmp_path):
        row = SimpleNamespace(task_type="audio.transcode", error="x", error_code="remote_error",
                              created_at="2026-07-04T00:00:00")
        with patch("app.services.feedback.diagnostics._history_get", return_value=row):
            d = build_diagnostics(settings=_mk_settings(tmp_path), task_manager=_mk_task_manager(None), task_id="t-2")
        assert "audio.transcode" in d.task_context

    def test_core_error_priority_budget(self, tmp_path):
        logs = tmp_path / "logs"; logs.mkdir()
        (logs / "core_error.log").write_bytes(b"E" * 50_000)
        (logs / "app.log").write_bytes(b"A" * 100_000)
        d = build_diagnostics(settings=_mk_settings(tmp_path), task_manager=_mk_task_manager(), task_id=None)
        raw = d.log_tail.encode("utf-8")
        assert len(raw) <= LOG_TAIL_CAP_BYTES                       # 不變量 (a)
        assert d.log_tail.count("E") <= CORE_ERROR_CAP_BYTES        # core 上限 10,240
        assert d.log_tail.count("A") > 25_000                       # 剩餘預算給 app.log

    def test_app_log_missing_budget_goes_to_core(self, tmp_path):
        logs = tmp_path / "logs"; logs.mkdir()
        (logs / "core_error.log").write_bytes(b"E" * 50_000)        # 只有 core
        d = build_diagnostics(settings=_mk_settings(tmp_path), task_manager=_mk_task_manager(), task_id=None)
        assert d.log_tail.count("E") > CORE_ERROR_CAP_BYTES         # 餘額歸 core
        assert len(d.log_tail.encode("utf-8")) <= LOG_TAIL_CAP_BYTES

    def test_mask_before_truncate_invariant(self, tmp_path):
        # 不變量 (a) 完整版：短 username 遮成 *** 變長，最壞輸入仍 ≤ 40,960 bytes
        logs = tmp_path / "logs"; logs.mkdir()
        line = b"C:\\Users\\ab\\f.mp4 fail\n"     # username 2 chars → *** 變長
        (logs / "app.log").write_bytes(line * 5_000)
        d = build_diagnostics(settings=_mk_settings(tmp_path), task_manager=_mk_task_manager(), task_id=None)
        assert len(d.log_tail.encode("utf-8")) <= LOG_TAIL_CAP_BYTES
        assert "\\ab\\" not in d.log_tail

    def test_app_version_populated(self, tmp_path, monkeypatch):
        monkeypatch.setenv("MEDIATRANX_APP_VERSION", "1.2.3")
        d = build_diagnostics(settings=_mk_settings(tmp_path), task_manager=_mk_task_manager(), task_id=None)
        assert d.app_version == "1.2.3"
