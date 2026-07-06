"""POST /feedback、GET /feedback/diagnostics、export 的 API 測試。"""
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.handler.error_responses import register_exception_handlers
from app.handler.exceptions import FeedbackTransportError
from app.init.container import AppContainer
from app.services.feedback.config import POST_SECTION_CHAR_LIMIT, LOG_TAIL_CAP_BYTES
from app.services.feedback.diagnostics import DiagnosticsSections
from app.services.feedback.service import FeedbackService


def _sections(**kw):
    base = dict(app_version="1.0.0", env_summary="env", task_context="(無)", log_tail="log")
    base.update(kw)
    return DiagnosticsSections(**base)


@pytest.fixture()
def client():
    """真 FeedbackService + mock transport（服務邏輯要真跑：防禦遮罩/驗證/prefill）。"""
    transport = MagicMock()
    container = AppContainer()
    svc = FeedbackService(task_manager=MagicMock(), transport=transport)
    container.feedback.override(svc)
    from app.api.routes.feedback import router as feedback_router
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(feedback_router)
    container.wire(modules=["app.api.routes.feedback.feedback"])
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c, transport
    container.unwire()
    container.feedback.reset_override()


def _body(**kw):
    base = dict(type="bug", description="它壞了", include_diagnostics=True,
                diagnostics=_sections().model_dump())
    base.update(kw)
    return base


class TestSubmit:
    def test_happy_path_204(self, client):
        c, transport = client
        r = c.post("/feedback", json=_body())
        assert r.status_code == 204
        report = transport.submit.call_args[0][0]
        assert report.type_label == "問題回報"

    def test_empty_description_400(self, client):
        c, _ = client
        assert c.post("/feedback", json=_body(description="  ")).status_code == 400

    def test_unknown_type_400(self, client):
        c, _ = client
        assert c.post("/feedback", json=_body(type="nope")).status_code == 400

    def test_include_diag_without_snapshot_400(self, client):
        c, _ = client
        assert c.post("/feedback", json=_body(diagnostics=None)).status_code == 400

    def test_no_diagnostics_backend_fills_version(self, client, monkeypatch):
        monkeypatch.setenv("MEDIATRANX_APP_VERSION", "7.7.7")
        c, transport = client
        r = c.post("/feedback", json=_body(include_diagnostics=False, diagnostics=None))
        assert r.status_code == 204
        report = transport.submit.call_args[0][0]
        assert report.app_version == "7.7.7"       # false 時後端自產
        assert report.sections is None

    def test_snapshot_sent_verbatim_with_idempotent_mask(self, client):
        # 「所見即所送」：帶回的 sections 原樣送出（已遮罩文字不改變）；
        # 防禦性遮罩對漏網 username 仍生效
        c, transport = client
        sec = _sections(env_summary=r"masked C:\Users\*** raw C:\Users\willie")
        r = c.post("/feedback", json=_body(diagnostics=sec.model_dump()))
        assert r.status_code == 204
        sent = transport.submit.call_args[0][0].sections
        assert sent.env_summary == r"masked C:\Users\*** raw C:\Users\***"
        assert sent.log_tail == "log"               # 其餘節原樣
        assert sent.app_version == "1.0.0"          # true 時用快照 app_version（零重組不變量）

    def test_accepts_full_size_snapshot(self, client):
        # 不變量 (b)：滿載（40,960 bytes）GET 快照不被誤拒
        c, _ = client
        big = "x" * LOG_TAIL_CAP_BYTES
        assert c.post("/feedback", json=_body(diagnostics=_sections(log_tail=big).model_dump())).status_code == 204

    def test_rejects_oversize_section(self, client):
        # 不變量 (c)：單節 > 50,000 字元拒絕
        c, _ = client
        huge = "x" * (POST_SECTION_CHAR_LIMIT + 1)
        assert c.post("/feedback", json=_body(diagnostics=_sections(log_tail=huge).model_dump())).status_code == 400

    def test_transport_failure_502_with_prefill(self, client):
        c, transport = client
        transport.submit.side_effect = FeedbackTransportError("form_network_error", "boom")
        r = c.post("/feedback", json=_body())
        assert r.status_code == 502
        data = r.json()
        assert data["error_code"] == "form_network_error"
        assert data["prefill_url"].startswith("https://docs.google.com/forms/")

    def test_prefill_on_failure_without_diagnostics_omits_env(self, client):
        c, transport = client
        transport.submit.side_effect = FeedbackTransportError("form_network_error", "boom")
        r = c.post("/feedback", json=_body(include_diagnostics=False, diagnostics=None))
        from app.services.feedback.config import ENTRY_IDS
        assert ENTRY_IDS["env_summary"] not in r.json()["prefill_url"]


class TestDiagnostics:
    def test_get_diagnostics_returns_sections(self, client):
        c, _ = client
        with patch("app.services.feedback.service.build_diagnostics", return_value=_sections()):
            r = c.get("/feedback/diagnostics")
        assert r.status_code == 200
        assert set(r.json().keys()) == {"app_version", "env_summary", "task_context", "log_tail"}

    def test_export_returns_zip_path(self, client, tmp_path):
        c, _ = client
        with patch("app.services.feedback.service.FeedbackService.export_diagnostics",
                   return_value=str(tmp_path / "d.zip")):
            r = c.post("/feedback/diagnostics/export")
        assert r.status_code == 200
        assert r.json()["zip_path"].endswith("d.zip")


class TestExportZip:
    def test_export_zips_logs_and_sysinfo_unmasked(self, tmp_path, monkeypatch):
        import zipfile
        from types import SimpleNamespace
        svc = FeedbackService(task_manager=MagicMock(), transport=MagicMock())
        log_dir = tmp_path / "logs"; log_dir.mkdir()
        (log_dir / "app.log").write_text(r"raw C:\Users\willie path", encoding="utf-8")
        fake_settings = SimpleNamespace(path=SimpleNamespace(log=log_dir, temp=tmp_path / "temp"))
        monkeypatch.setattr("app.services.feedback.service.SETTINGS", fake_settings, raising=False)
        zip_path = svc.export_diagnostics()
        with zipfile.ZipFile(zip_path) as zf:
            names = zf.namelist()
            assert "app.log" in names and "system_info.txt" in names
            assert "willie" in zf.read("app.log").decode("utf-8")   # 匯出不遮罩
