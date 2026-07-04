"""診斷資料組裝：遮罩、tail 讀取、DiagnosticsSections。"""
import logging
import re
from pathlib import Path

from pydantic import BaseModel

logger = logging.getLogger(__name__)


class DiagnosticsSections(BaseModel):
    """對映 Google 表單欄位 4/5/6/7 的四節獨立字串。"""

    app_version: str
    env_summary: str
    task_context: str
    log_tail: str


# <磁碟代號>:[\/]Users[\/]<name> 與 UNC \\<host>[\/]Users[\/]<name>
# <name> 結束於路徑分隔符或行尾/空白/引號/;,)] 邊界（用排除字元類實現，
# 不錨定尾隨分隔符——路徑在行尾時沒有它）。對 *** 冪等（* 不在排除類中）。
_USER_PATH_RE = re.compile(
    r"(?P<prefix>(?:[A-Za-z]:|\\\\[^\\/\s\"';,)\]]+)[\\/]+Users[\\/]+)"
    r"(?P<name>[^\\/\s\"';,)\]]+)",
    re.IGNORECASE,
)


def redact_usernames(text: str) -> str:
    """把使用者路徑中的 <name> 換成 ***。冪等。"""
    return _USER_PATH_RE.sub(lambda m: m.group("prefix") + "***", text)


def read_tail_bytes(path: Path, max_bytes: int) -> bytes | None:
    """seek-from-end 讀檔案尾段。檔案不存在或讀取失敗回 None，永不 raise。

    app.log 是跨執行累積、無 rotation 的 append 檔（可能數十 MB），
    不得整檔讀入。Electron 以 append 模式持有中，Windows read-share 下並行讀取安全。
    """
    try:
        if not path.is_file():
            return None
        size = path.stat().st_size
        with path.open("rb") as f:
            if size > max_bytes:
                f.seek(size - max_bytes)
            return f.read(max_bytes)
    except OSError:
        logger.warning("feedback: failed to read log tail: %s", path)
        return None


def truncate_utf8_tail(text: str, cap_bytes: int) -> str:
    """保留字串尾端、以 bytes 計截斷，切點落在 UTF-8 字元邊界。"""
    data = text.encode("utf-8")
    if len(data) <= cap_bytes:
        return text
    cut = data[len(data) - cap_bytes:]
    # 跳過開頭的 UTF-8 continuation bytes（0b10xxxxxx）
    i = 0
    while i < len(cut) and (cut[i] & 0xC0) == 0x80:
        i += 1
    return cut[i:].decode("utf-8")
