"""Tests for access-log secret redaction.

Defense-in-depth: even if a secret (api_key / token / ...) ends up in a request
URL's query string, the uvicorn access log must never record its value — a 422
on the old leaky URL still logs the full request line, so rejecting isn't enough.
"""
import logging

from app.init.logging_config import RedactSecretsFilter


def _access_record(path: str) -> logging.LogRecord:
    """Mimic a uvicorn.access log record (5-tuple args, path carries query)."""
    return logging.LogRecord(
        name="uvicorn.access", level=logging.INFO, pathname="", lineno=0,
        msg='%s - "%s %s HTTP/%s" %d',
        args=("127.0.0.1:50000", "GET", path, "1.1", 422),
        exc_info=None,
    )


def test_redacts_api_key_value_keeps_other_params():
    f = RedactSecretsFilter()
    rec = _access_record("/api/setup/remote/models?provider=openai&api_key=sk-secret123&x=1")
    assert f.filter(rec) is True
    msg = rec.getMessage()
    assert "sk-secret123" not in msg
    assert "api_key=***" in msg
    assert "provider=openai" in msg  # non-secret params untouched
    assert "x=1" in msg


def test_redacts_common_secret_param_variants():
    f = RedactSecretsFilter()
    cases = {
        "token=abc.def.ghi": "abc.def.ghi",
        "api-key=sk-1": "sk-1",
        "key=AIzaSyLEAK": "AIzaSyLEAK",
        "password=hunter2": "hunter2",
    }
    for qs, secret in cases.items():
        rec = _access_record(f"/x?{qs}")
        f.filter(rec)
        assert secret not in rec.getMessage(), f"{qs} leaked"


def test_clean_url_and_argless_record_untouched():
    f = RedactSecretsFilter()
    rec = _access_record("/api/health")
    f.filter(rec)
    assert rec.getMessage().endswith('"GET /api/health HTTP/1.1" 422')
    # A record with no args must not crash the filter.
    plain = logging.LogRecord("x", logging.INFO, "", 0, "plain message", None, None)
    assert f.filter(plain) is True
