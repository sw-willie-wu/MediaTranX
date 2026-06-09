"""OpenAIProvider cancel tests — abort_hook + socket close.

Spec §F1 + §4.2.
"""
import json
import threading
from unittest.mock import MagicMock, patch

import pytest


def test_chat_completions_streaming_invokes_abort_hook_with_resp():
    """abort_hook receives the live response object exactly once before iteration."""
    from app.adapters.ai.remote.openai import OpenAIProvider

    resp = MagicMock(name="HTTPResponse")
    resp.__iter__ = lambda self: iter([b'data: [DONE]\n'])
    resp.__enter__ = MagicMock(return_value=resp)
    resp.__exit__ = MagicMock(return_value=False)
    resp.close = MagicMock()

    received = []
    def hook(r):
        received.append(r)

    with patch(
        "app.adapters.ai.remote._http.urlopen",
        return_value=resp,
    ):
        prov = OpenAIProvider("https://api.openai.com", "sk-test")
        prov.chat(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": "x"}],
            max_tokens=10, temperature=0.0,
            abort_hook=hook,
        )
    assert received == [resp]


def test_chat_completions_streaming_oserror_translated_to_connection_failed():
    """When abort_hook closes the response, iteration raises OSError → connection_failed."""
    from app.adapters.ai.remote.openai import OpenAIProvider
    from app.handler.exceptions import RemoteApiError

    # Use MagicMock(side_effect=...) — assigning a raw function to __iter__
    # on a MagicMock binds it as (self,) which gives TypeError, not OSError.
    # Pattern mirrors tests/adapters/ai/remote/test_ollama_streaming.py:124.
    resp = MagicMock(name="HTTPResponse")
    resp.__iter__ = MagicMock(side_effect=OSError("socket closed mid-read"))
    resp.__enter__ = MagicMock(return_value=resp)
    resp.__exit__ = MagicMock(return_value=False)
    resp.close = MagicMock()

    with patch(
        "app.adapters.ai.remote._http.urlopen",
        return_value=resp,
    ):
        prov = OpenAIProvider("https://api.openai.com", "sk-test")
        with pytest.raises(RemoteApiError) as exc_info:
            prov.chat(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": "x"}],
                max_tokens=10, temperature=0.0,
                abort_hook=lambda r: None,
            )
    assert exc_info.value.code == "connection_failed"


def test_responses_streaming_invokes_abort_hook_with_resp():
    """Responses-API path also stashes resp via abort_hook."""
    from app.adapters.ai.remote.openai import OpenAIProvider

    resp = MagicMock(name="HTTPResponse")
    resp.__iter__ = lambda self: iter([
        b'event: response.completed\n', b'data: {}\n',
    ])
    resp.__enter__ = MagicMock(return_value=resp)
    resp.__exit__ = MagicMock(return_value=False)
    resp.close = MagicMock()

    received = []
    with patch(
        "app.adapters.ai.remote._http.urlopen",
        return_value=resp,
    ):
        prov = OpenAIProvider("https://api.openai.com", "sk-test")
        prov.chat(
            model="o4-mini",
            messages=[{"role": "user", "content": "x"}],
            max_tokens=10, temperature=0.0,
            abort_hook=lambda r: received.append(r),
        )
    assert received == [resp]
