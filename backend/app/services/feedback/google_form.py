"""Google 表單 transport：formResponse 直送 + 降級 viewform 預填連結。"""
import logging
import urllib.error
import urllib.parse
from urllib.request import Request, urlopen

from app.handler.exceptions import FeedbackTransportError
from app.services.feedback.config import (
    EMPTY_SECTION,
    ENTRY_IDS,
    FORM_TIMEOUT_S,
    PREFILL_URL_CAP_BYTES,
    form_response_url,
    viewform_url,
)
from app.services.feedback.transport import FeedbackReport, FeedbackTransport

logger = logging.getLogger(__name__)


class GoogleFormTransport(FeedbackTransport):
    def submit(self, report: FeedbackReport) -> None:
        data: dict[str, str] = {
            ENTRY_IDS["type"]: report.type_label,
            ENTRY_IDS["description"]: report.description,
            ENTRY_IDS["app_version"]: report.app_version,
            # Google 表單提交輔助欄位（fbzx 可省略，e2e 以測試表單實測定案）
            "fvv": "1",
            "pageHistory": "0",
            "submit": "Submit",
        }
        if report.email:
            data[ENTRY_IDS["email"]] = report.email
        if report.include_diagnostics and report.sections is not None:
            data[ENTRY_IDS["env_summary"]] = report.sections.env_summary
            data[ENTRY_IDS["task_context"]] = report.sections.task_context
            data[ENTRY_IDS["log_tail"]] = report.sections.log_tail

        body = urllib.parse.urlencode(data).encode("utf-8")
        req = Request(
            form_response_url(),
            data=body,
            headers={"Content-Type": "application/x-www-form-urlencoded; charset=utf-8"},
        )
        # 已知限制（spec §3.1）：Google 對「停止接受回應/必填被拒」也可能回 200+HTML
        # 錯誤頁，runtime 無法可靠區分；由 e2e 直驗 Sheet 收到來把關。
        try:
            with urlopen(req, timeout=FORM_TIMEOUT_S) as resp:
                status = getattr(resp, "status", None) or resp.getcode()
                if status != 200:
                    raise FeedbackTransportError("form_http_error", f"HTTP {status}")
        except FeedbackTransportError:
            raise
        except urllib.error.HTTPError as e:
            raise FeedbackTransportError("form_http_error", f"HTTP {e.code}") from e
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            raise FeedbackTransportError("form_network_error", str(e)) from e


def _render(fields: list[tuple[str, str]]) -> str:
    qs = "".join(f"&{k}={urllib.parse.quote(v)}" for k, v in fields)
    return f"{viewform_url()}?usp=pp_url{qs}"


def build_prefill_url(report: FeedbackReport) -> str:
    """降級用官方預填連結。cap 6KB，超過依序砍：環境摘要 → 任務脈絡 → 截描述。

    Log 尾段永不進 prefill。
    """
    fields: list[tuple[str, str]] = [
        (ENTRY_IDS["type"], report.type_label),
        (ENTRY_IDS["description"], report.description),
    ]
    if report.email:
        fields.append((ENTRY_IDS["email"], report.email))
    fields.append((ENTRY_IDS["app_version"], report.app_version))
    if report.include_diagnostics and report.sections is not None:
        # 任務入口降級時不能丟掉 errorCode/error 訊息這個核心價值
        if report.sections.task_context != EMPTY_SECTION:
            fields.append((ENTRY_IDS["task_context"], report.sections.task_context))
        fields.append((ENTRY_IDS["env_summary"], report.sections.env_summary))

    def fits(fs: list[tuple[str, str]]) -> bool:
        return len(_render(fs).encode("utf-8")) <= PREFILL_URL_CAP_BYTES

    if fits(fields):
        return _render(fields)
    fields = [f for f in fields if f[0] != ENTRY_IDS["env_summary"]]          # 砍環境摘要
    if fits(fields):
        return _render(fields)
    fields = [f for f in fields if f[0] != ENTRY_IDS["task_context"]]         # 砍任務脈絡
    if fits(fields):
        return _render(fields)
    # 截描述：逐步縮短直到符合
    desc = report.description
    while desc and not fits([(k, (desc if k == ENTRY_IDS["description"] else v)) for k, v in fields]):
        desc = desc[: max(0, int(len(desc) * 0.8) - 1)]
    fields = [(k, (desc if k == ENTRY_IDS["description"] else v)) for k, v in fields]
    return _render(fields)
