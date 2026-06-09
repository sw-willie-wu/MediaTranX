"""Shared HTTP helper for remote providers.

`urlopen` is a drop-in for `urllib.request.urlopen` that REFUSES to silently
follow a cross-scheme http->https redirect. urllib follows 301s by downgrading
POST->GET, so an http:// endpoint behind an https redirect turns a POST /api/chat
into a GET -> 405, surfacing as a confusing generic error. A cross-scheme
redirect means the endpoint URL should be https; we raise a clear, actionable
error instead of following it (and so never re-send headers/body to the https
target ourselves).
"""
from __future__ import annotations

import urllib.request
from urllib.parse import urlparse

from app.handler.exceptions import RemoteApiError


class _CrossSchemeRedirect(Exception):
    """Internal signal: an http request was redirected to https."""
    def __init__(self, newurl: str):
        self.newurl = newurl
        super().__init__(newurl)


class _NoDowngradeRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if urlparse(req.full_url).scheme == "http" and urlparse(newurl).scheme == "https":
            raise _CrossSchemeRedirect(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


# Process-local opener (NOT install_opener — avoid a global side effect on all
# backend urllib usage). build_opener replaces the default redirect handler with
# our subclass.
_OPENER = urllib.request.build_opener(_NoDowngradeRedirectHandler)


def urlopen(req, *, timeout):
    """Drop-in for urllib.request.urlopen. Raises RemoteApiError on a
    cross-scheme http->https redirect; all other exceptions propagate
    unchanged so callers' existing except blocks keep working."""
    try:
        return _OPENER.open(req, timeout=timeout)
    except _CrossSchemeRedirect as e:
        raise RemoteApiError(
            "endpoint_https_redirect",
            f"Endpoint redirected http->https. Update the connection URL to "
            f"https://. (-> {e.newurl})",
        ) from None
