"""Unit tests for the cross-scheme redirect guard (_http.urlopen)."""
import urllib.request

import pytest

from app.adapters.ai.remote import _http
from app.handler.exceptions import RemoteApiError


def test_redirect_handler_raises_on_http_to_https():
    h = _http._NoDowngradeRedirectHandler()
    req = urllib.request.Request("http://example.com/api/chat", method="POST")
    with pytest.raises(_http._CrossSchemeRedirect):
        h.redirect_request(req, None, 301, "Moved Permanently", {},
                           "https://example.com/api/chat")


def test_redirect_handler_allows_same_scheme():
    h = _http._NoDowngradeRedirectHandler()
    req = urllib.request.Request("https://example.com/a")  # GET
    new = h.redirect_request(req, None, 301, "Moved Permanently", {},
                             "https://example.com/b")
    assert new is not None and new.full_url == "https://example.com/b"


def test_urlopen_translates_cross_scheme_to_remote_api_error(monkeypatch):
    def boom(req, timeout):
        raise _http._CrossSchemeRedirect("https://x/api/chat")
    monkeypatch.setattr(_http._OPENER, "open", boom)
    req = urllib.request.Request("http://x/api/chat")
    with pytest.raises(RemoteApiError) as ei:
        _http.urlopen(req, timeout=5)
    assert ei.value.code == "endpoint_https_redirect"
    assert "https://" in ei.value.detail
