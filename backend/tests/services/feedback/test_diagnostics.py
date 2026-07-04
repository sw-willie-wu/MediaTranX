"""diagnostics 低階工具：遮罩、UTF-8 邊界截斷、seek-tail。"""
from pathlib import Path

from app.services.feedback.diagnostics import (
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
