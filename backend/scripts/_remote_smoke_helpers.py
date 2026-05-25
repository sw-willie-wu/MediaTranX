"""Shared helpers for OpenAI/Gemini smoke + cancel harness scripts.

DB-first credential resolution: if `MTX_REMOTE_CONN_ID` is set, look up
the matching `api_connections` row and return an instantiated provider.
Otherwise fall back to env-var (`MTX_OPENAI_API_KEY` / `MTX_GEMINI_API_KEY`).

Mirrors the e2e scripts' pattern so the operator only needs to add a
connection in the UI once, then `$env:MTX_REMOTE_CONN_ID=<id>` covers
all smoke/cancel/e2e scripts uniformly.
"""
from __future__ import annotations
import os
import sys
from typing import Optional


def resolve_provider(
    provider_name: str,
    default_endpoint: str,
    env_var_for_api_key: str,
):
    """Return an instantiated provider for the given provider_name.

    Resolution order:
    1. `MTX_REMOTE_CONN_ID` env → ApiConnectionDAO lookup → endpoint+api_key from DB.
       Provider mismatch (e.g. conn_id points at gemini but caller asked
       for openai) returns None — caller treats as fatal.
    2. `MTX_<PROVIDER>_ENDPOINT` + env_var_for_api_key env → direct construction.
    3. Neither → print error to stderr + sys.exit(2).

    Args:
        provider_name: "openai" or "gemini".
        default_endpoint: e.g. "https://api.openai.com"; used when no
            MTX_<PROVIDER>_ENDPOINT env is set and falling back to env-var path.
        env_var_for_api_key: name of the env var that may hold the key.

    Returns:
        Constructed OpenAIProvider / GeminiProvider instance.
    """
    conn_id_env = os.environ.get("MTX_REMOTE_CONN_ID")
    if conn_id_env:
        from app.init.container import init_container

        container = init_container()
        prov = container.remote_service().get_provider_for_connection(
            int(conn_id_env), provider_name,
        )
        if prov is None:
            print(
                f"ERROR: MTX_REMOTE_CONN_ID={conn_id_env} not found in DB, "
                f"or provider mismatch (expected provider={provider_name!r}).",
                file=sys.stderr,
            )
            sys.exit(2)
        return prov

    # Fall back to env vars
    endpoint = os.environ.get(
        f"MTX_{provider_name.upper()}_ENDPOINT", default_endpoint,
    )
    api_key = os.environ.get(env_var_for_api_key)
    if not api_key:
        print(
            f"ERROR: set MTX_REMOTE_CONN_ID=<id> (preferred — pulls "
            f"endpoint + api_key from app DB) OR set {env_var_for_api_key}.",
            file=sys.stderr,
        )
        sys.exit(2)

    if provider_name == "openai":
        from app.adapters.ai.remote.openai import OpenAIProvider
        return OpenAIProvider(endpoint, api_key)
    if provider_name == "gemini":
        from app.adapters.ai.remote.gemini import GeminiProvider
        return GeminiProvider(endpoint, api_key)
    print(f"ERROR: unknown provider_name={provider_name!r}", file=sys.stderr)
    sys.exit(2)
