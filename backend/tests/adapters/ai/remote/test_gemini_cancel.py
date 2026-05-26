"""GeminiProvider cancel tests — abort_hook + socket close.

Spec §4.3.
"""
from unittest.mock import MagicMock, patch

import pytest


def test_streaming_invokes_abort_hook_with_resp():
    from app.adapters.ai.remote.gemini import GeminiProvider

    resp = MagicMock(name="HTTPResponse")
    resp.__iter__ = lambda self: iter([])
    resp.__enter__ = MagicMock(return_value=resp)
    resp.__exit__ = MagicMock(return_value=False)
    resp.close = MagicMock()

    received = []
    with patch(
        "app.adapters.ai.remote.gemini.urllib.request.urlopen",
        return_value=resp,
    ):
        prov = GeminiProvider(
            "https://generativelanguage.googleapis.com", "AIza-test",
        )
        prov.chat(
            model="gemini-2.5-flash",
            messages=[{"role": "user", "content": "x"}],
            max_tokens=10, temperature=0.0,
            abort_hook=lambda r: received.append(r),
        )
    assert received == [resp]


def test_streaming_oserror_translated_to_connection_failed():
    from app.adapters.ai.remote.gemini import GeminiProvider
    from app.handler.exceptions import RemoteApiError

    # See OpenAI cancel test sibling — must use MagicMock(side_effect=) not
    # a raw function (raw fn binds as (self,) → TypeError).
    resp = MagicMock(name="HTTPResponse")
    resp.__iter__ = MagicMock(side_effect=OSError("socket closed mid-read"))
    resp.__enter__ = MagicMock(return_value=resp)
    resp.__exit__ = MagicMock(return_value=False)
    resp.close = MagicMock()

    with patch(
        "app.adapters.ai.remote.gemini.urllib.request.urlopen",
        return_value=resp,
    ):
        prov = GeminiProvider(
            "https://generativelanguage.googleapis.com", "AIza-test",
        )
        with pytest.raises(RemoteApiError) as exc_info:
            prov.chat(
                model="gemini-2.5-flash",
                messages=[{"role": "user", "content": "x"}],
                max_tokens=10, temperature=0.0,
                abort_hook=lambda r: None,
            )
    assert exc_info.value.code == "connection_failed"
