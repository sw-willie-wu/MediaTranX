"""診斷資料組裝：遮罩、tail 讀取、DiagnosticsSections。"""
import logging
import re
from pathlib import Path
from urllib.parse import quote_plus

from pydantic import BaseModel

from app.init.system_info import app_version, collect_env_summary
from app.services.feedback.config import (
    CORE_ERROR_CAP_BYTES,
    EMPTY_SECTION,
    ENV_ENCODED_BUDGET,
    LOG_TAIL_CAP_BYTES,
    LOG_TAIL_ENCODED_BUDGET,
    SECTION_ASSEMBLY_CHAR_CAP,
    TASK_ENCODED_BUDGET,
)

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


def _history_get(task_id: str):
    """從 history DB 查單筆；獨立函式方便測試 patch。"""
    from app.db.dao.task_history_dao import TaskHistoryDAO  # 延遲 import 避免啟動連鎖
    try:
        return TaskHistoryDAO().get(task_id)
    except Exception:
        logger.warning("feedback: history lookup failed for %s", task_id)
        return None


def _build_task_context(task_id: str | None, task_manager) -> str:
    if not task_id:
        return EMPTY_SECTION
    task = task_manager.get_task(task_id)
    if task is None:
        task = _history_get(task_id)
    if task is None:
        return EMPTY_SECTION
    created = getattr(task, "created_at", None)
    created_s = created.isoformat() if hasattr(created, "isoformat") else str(created or EMPTY_SECTION)
    return "\n".join([
        f"task_type: {getattr(task, 'task_type', EMPTY_SECTION)}",
        f"error_code: {getattr(task, 'error_code', None) or EMPTY_SECTION}",
        f"error: {getattr(task, 'error', None) or EMPTY_SECTION}",
        f"created_at: {created_s}",
    ])


def _decode(raw: bytes) -> str:
    return raw.decode("utf-8", errors="replace")


def truncate_to_encoded_budget(text: str, budget_bytes: int, *, keep: str = "tail") -> str:
    """以 form-urlencoded（quote_plus）後的大小為預算截斷。

    Google formResponse 的 body 上限 ~31KB 是以「編碼後」計的——CJK 每字元
    編碼成 9 chars（×3 膨脹），原始 bytes cap 擋不住 413。字元級切片保證
    不會切壞 UTF-8。keep='tail' 保尾端（log 最新行）、'head' 保頭端
    （env/task 的關鍵欄位在前面）。
    """
    if len(quote_plus(text).encode()) <= budget_bytes:
        return text
    lo, hi = 0, len(text)  # 二分找最大可保留字元數
    while lo < hi:
        mid = (lo + hi + 1) // 2
        piece = text[-mid:] if keep == "tail" else text[:mid]
        if len(quote_plus(piece).encode()) <= budget_bytes:
            lo = mid
        else:
            hi = mid - 1
    if lo == 0:
        return ""
    return text[-lo:] if keep == "tail" else text[:lo]


def _build_log_tail(log_dir: Path) -> str:
    """兩檔 tail 合併：core_error.log 優先（上限 10,240 bytes）、餘額給 app.log。

    順序固定：先遮罩、後截斷（遮罩會讓字串變長，先截會破組裝 cap 不變量）。
    原始 tail 讀比預算多（×2）以吸收遮罩造成的長度變化。
    """
    core_raw = read_tail_bytes(log_dir / "core_error.log", LOG_TAIL_CAP_BYTES * 2)
    app_raw = read_tail_bytes(log_dir / "app.log", LOG_TAIL_CAP_BYTES * 2)

    header_core = "=== core_error.log ===\n"
    header_app = "\n\n=== app.log ===\n"
    headers_bytes = len(header_core.encode()) + len(header_app.encode())

    # 某檔不存在時，餘額歸另一檔（扣掉 headers 與缺檔節的 "(無)" 佔位）
    empty_bytes = len(EMPTY_SECTION.encode("utf-8"))
    core_budget = (
        CORE_ERROR_CAP_BYTES if app_raw is not None
        else LOG_TAIL_CAP_BYTES - headers_bytes - empty_bytes
    )
    core_text = (
        EMPTY_SECTION if core_raw is None
        else truncate_utf8_tail(redact_usernames(_decode(core_raw)), core_budget)
    )
    remaining = LOG_TAIL_CAP_BYTES - headers_bytes - len(core_text.encode("utf-8"))
    app_text = (
        EMPTY_SECTION if app_raw is None
        else truncate_utf8_tail(redact_usernames(_decode(app_raw)), max(0, remaining))
    )
    combined = header_core + core_text + header_app + app_text
    # 保險截斷（原始 bytes 上限）後，再壓進 form-encoded 預算（413 防線，保尾端）
    combined = truncate_utf8_tail(combined, LOG_TAIL_CAP_BYTES)
    return truncate_to_encoded_budget(combined, LOG_TAIL_ENCODED_BUDGET, keep="tail")


def build_diagnostics(*, settings, task_manager, task_id: str | None) -> DiagnosticsSections:
    """組裝四節診斷。只在 GET /feedback/diagnostics 呼叫（所見即所送的快照來源）。

    各節同時受字元 cap 與 form-encoded 預算限制——後者是 Google formResponse
    body ~31KB 上限（413）的防線，在組裝端截以維持「預覽 = 送出」。
    """
    env = redact_usernames(collect_env_summary(settings))[:SECTION_ASSEMBLY_CHAR_CAP]
    env = truncate_to_encoded_budget(env, ENV_ENCODED_BUDGET, keep="head")
    ctx = redact_usernames(_build_task_context(task_id, task_manager))[:SECTION_ASSEMBLY_CHAR_CAP]
    ctx = truncate_to_encoded_budget(ctx, TASK_ENCODED_BUDGET, keep="head")
    return DiagnosticsSections(
        app_version=app_version(),
        env_summary=env,
        task_context=ctx,
        log_tail=_build_log_tail(settings.path.log),
    )
