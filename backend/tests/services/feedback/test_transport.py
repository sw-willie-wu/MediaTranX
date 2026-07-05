"""GoogleFormTransport（patch urlopen）與 build_prefill_url。"""
import urllib.error
import urllib.parse
from unittest.mock import MagicMock, patch

import pytest

from app.handler.exceptions import FeedbackTransportError
from app.services.feedback.config import ENTRY_IDS, PREFILL_URL_CAP_BYTES, TYPE_LABELS
from app.services.feedback.diagnostics import DiagnosticsSections
from app.services.feedback.google_form import GoogleFormTransport, build_prefill_url
from app.services.feedback.transport import FeedbackReport


def _sections(env="env", ctx="ctx", log="log"):
    return DiagnosticsSections(app_version="1.0.0", env_summary=env, task_context=ctx, log_tail=log)


def _report(**kw):
    base = dict(
        type_label=TYPE_LABELS["bug"], description="它壞了", email=None,
        include_diagnostics=True, sections=_sections(), app_version="1.0.0",
    )
    base.update(kw)
    return FeedbackReport(**base)


def _ok_response():
    resp = MagicMock()
    resp.status = 200
    resp.__enter__ = lambda s: s
    resp.__exit__ = lambda s, *a: False
    return resp


class TestGoogleFormTransport:
    def test_submit_posts_all_entries(self):
        with patch("app.services.feedback.google_form.urlopen", return_value=_ok_response()) as mock:
            GoogleFormTransport().submit(_report(email="a@b.c"))
        req = mock.call_args[0][0]
        body = urllib.parse.parse_qs(req.data.decode("utf-8"))
        assert body[ENTRY_IDS["type"]] == ["問題回報"]
        assert body[ENTRY_IDS["description"]] == ["它壞了"]
        assert body[ENTRY_IDS["email"]] == ["a@b.c"]
        assert body[ENTRY_IDS["app_version"]] == ["1.0.0"]
        assert body[ENTRY_IDS["env_summary"]] == ["env"]
        assert body[ENTRY_IDS["task_context"]] == ["ctx"]
        assert body[ENTRY_IDS["log_tail"]] == ["log"]
        # Google 表單提交輔助欄位
        assert body["fvv"] == ["1"]
        assert body["pageHistory"] == ["0"]
        assert "formResponse" in req.full_url

    def test_submit_without_diagnostics_omits_567(self):
        with patch("app.services.feedback.google_form.urlopen", return_value=_ok_response()) as mock:
            GoogleFormTransport().submit(_report(include_diagnostics=False, sections=None))
        body = urllib.parse.parse_qs(mock.call_args[0][0].data.decode("utf-8"))
        assert ENTRY_IDS["env_summary"] not in body
        assert ENTRY_IDS["task_context"] not in body
        assert ENTRY_IDS["log_tail"] not in body
        assert body[ENTRY_IDS["app_version"]] == ["1.0.0"]   # 欄位 4 永遠送

    def test_http_error_raises(self):
        err = urllib.error.HTTPError("u", 404, "nf", {}, None)
        with patch("app.services.feedback.google_form.urlopen", side_effect=err):
            with pytest.raises(FeedbackTransportError) as ei:
                GoogleFormTransport().submit(_report())
        assert ei.value.code == "form_http_error"

    def test_network_error_raises(self):
        with patch("app.services.feedback.google_form.urlopen",
                   side_effect=urllib.error.URLError("timeout")):
            with pytest.raises(FeedbackTransportError) as ei:
                GoogleFormTransport().submit(_report())
        assert ei.value.code == "form_network_error"


class TestBuildPrefillUrl:
    def test_contains_short_fields_never_log(self):
        url = build_prefill_url(_report(email="a@b.c"))
        assert "usp=pp_url" in url and "viewform" in url
        assert ENTRY_IDS["type"] in url and ENTRY_IDS["description"] in url
        assert ENTRY_IDS["email"] in url and ENTRY_IDS["app_version"] in url
        assert ENTRY_IDS["env_summary"] in url and ENTRY_IDS["task_context"] in url
        assert ENTRY_IDS["log_tail"] not in url            # log 永不進 prefill

    def test_no_diagnostics_omits_env_and_ctx(self):
        url = build_prefill_url(_report(include_diagnostics=False, sections=None))
        assert ENTRY_IDS["env_summary"] not in url
        assert ENTRY_IDS["task_context"] not in url

    def test_values_urlencoded(self):
        url = build_prefill_url(_report(description="有 空格&符號"))
        assert " " not in url.split("?", 1)[1]

    def test_cap_drops_env_first(self):
        url = build_prefill_url(_report(sections=_sections(env="E" * 10_000, ctx="c")))
        assert len(url.encode()) <= PREFILL_URL_CAP_BYTES
        assert ENTRY_IDS["env_summary"] not in url
        assert ENTRY_IDS["task_context"] in url            # ctx 短，保留

    def test_cap_drops_ctx_second(self):
        url = build_prefill_url(_report(sections=_sections(env="E" * 10_000, ctx="C" * 10_000)))
        assert len(url.encode()) <= PREFILL_URL_CAP_BYTES
        assert ENTRY_IDS["env_summary"] not in url
        assert ENTRY_IDS["task_context"] not in url

    def test_cap_truncates_description_last(self):
        url = build_prefill_url(_report(description="D" * 20_000, include_diagnostics=False, sections=None))
        assert len(url.encode()) <= PREFILL_URL_CAP_BYTES
        assert ENTRY_IDS["description"] in url             # 描述被截、不被砍
