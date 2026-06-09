"""Shared HTTP-stub helpers for RemoteProvider tests.

Patches `_http.urlopen` (the shared cross-scheme redirect guard the providers
route through); helpers below build `urlopen()`-shaped fakes (response object usable as a context manager
yielding a `.read()`-able). The response object is re-enterable so a single
`make_response(...)` can be passed to `patch(..., return_value=...)` and used
across multiple `urlopen` calls without exhausting a generator.
"""
from __future__ import annotations

import io
import json
import urllib.error
from typing import Iterable


class _ReusableResponse:
    """`urlopen()` result that can be re-entered as a context manager.

    Each `with` block yields self; `.read()` returns the full body; iteration
    yields one line per call (matches the stdlib `addinfourl` iter protocol).
    """
    def __init__(self, body: bytes):
        self._body = body

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self) -> bytes:
        return self._body

    def __iter__(self) -> Iterable[bytes]:
        # Yield raw lines (no extra trailing newline added — match urllib)
        for line in self._body.splitlines():
            if line:
                yield line + b"\n"


def make_response(payload) -> _ReusableResponse:
    """Build a fake urlopen() result.

    `payload` may be a dict (JSON-serialized), bytes, or str.
    """
    if isinstance(payload, (bytes, bytearray)):
        body = bytes(payload)
    elif isinstance(payload, str):
        body = payload.encode("utf-8")
    else:
        body = json.dumps(payload).encode("utf-8")
    return _ReusableResponse(body)


def make_http_error(code: int, body: str | bytes = "", url: str = "https://x/") -> urllib.error.HTTPError:
    """Build a real urllib HTTPError whose `.read()` returns `body`."""
    body_bytes = body.encode("utf-8") if isinstance(body, str) else body
    return urllib.error.HTTPError(
        url=url,
        code=code,
        msg="error",
        hdrs=None,  # type: ignore[arg-type]
        fp=io.BytesIO(body_bytes),
    )


def make_url_error(reason: str = "Network unreachable") -> urllib.error.URLError:
    return urllib.error.URLError(reason)
