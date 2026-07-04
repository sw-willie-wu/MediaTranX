"""FeedbackService：三個 API 的 orchestration。"""
import logging
import zipfile
from datetime import datetime

from app.handler.exceptions import FeedbackSubmitError, FeedbackTransportError
from app.init.configs import SETTINGS
from app.init.system_info import app_version, collect_env_summary
from app.services.feedback.config import POST_SECTION_CHAR_LIMIT, TYPE_LABELS
from app.services.feedback.diagnostics import (
    DiagnosticsSections,
    build_diagnostics,
    redact_usernames,
)
from app.services.feedback.google_form import build_prefill_url
from app.services.feedback.transport import FeedbackReport, FeedbackTransport

logger = logging.getLogger(__name__)


class FeedbackService:
    def __init__(self, task_manager, transport: FeedbackTransport):
        self._task_manager = task_manager
        self._transport = transport

    def get_diagnostics(self, task_id: str | None) -> DiagnosticsSections:
        return build_diagnostics(
            settings=SETTINGS, task_manager=self._task_manager, task_id=task_id
        )

    def submit(
        self,
        *,
        type: str,
        description: str,
        email: str | None,
        include_diagnostics: bool,
        diagnostics: DiagnosticsSections | None,
    ) -> None:
        # 驗證（ValueError → 全域 handler 400）
        if type not in TYPE_LABELS:
            raise ValueError(f"unknown feedback type: {type}")
        if not description.strip():
            raise ValueError("description is required")
        if include_diagnostics and diagnostics is None:
            raise ValueError("include_diagnostics=true requires diagnostics snapshot")

        sections: DiagnosticsSections | None = None
        if include_diagnostics and diagnostics is not None:
            # 防禦性處理：逐節冪等重遮罩 + size 驗證。不重組（所見即所送）。
            sections = DiagnosticsSections(
                app_version=diagnostics.app_version,
                env_summary=redact_usernames(diagnostics.env_summary),
                task_context=redact_usernames(diagnostics.task_context),
                log_tail=redact_usernames(diagnostics.log_tail),
            )
            for name, value in sections.model_dump().items():
                if len(value) > POST_SECTION_CHAR_LIMIT:
                    raise ValueError(f"diagnostics section too large: {name}")

        report = FeedbackReport(
            type_label=TYPE_LABELS[type],
            description=description,
            email=email or None,
            include_diagnostics=include_diagnostics and sections is not None,
            sections=sections,
            # true 時用快照原樣（零重組不變量）；false 時後端自產
            app_version=sections.app_version if sections is not None else app_version(),
        )
        try:
            self._transport.submit(report)
        except FeedbackTransportError as e:
            logger.warning("feedback submit failed: %s", e)
            raise FeedbackSubmitError(e.code, e.detail, build_prefill_url(report)) from e

    def export_diagnostics(self) -> str:
        """打包 logs/ 全檔 + system info 成 zip 到 temp。不遮罩（原始檔）。"""
        out_dir = SETTINGS.path.temp / "feedback"
        out_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        zip_path = out_dir / f"diagnostics_{ts}.zip"
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            log_dir = SETTINGS.path.log
            if log_dir.is_dir():
                for p in sorted(log_dir.iterdir()):
                    if p.is_file():
                        try:
                            zf.write(p, arcname=p.name)
                        except OSError:
                            logger.warning("feedback export: skip unreadable %s", p)
            info = f"App 版本: {app_version()}\n{collect_env_summary(SETTINGS)}"
            zf.writestr("system_info.txt", info)
        # 絕對路徑：dev 模式 temp 是相對路徑，shell.showItemInFolder 需絕對路徑才能開資料夾
        return str(zip_path.resolve())
