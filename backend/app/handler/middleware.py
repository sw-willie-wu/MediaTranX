"""
Request lifecycle middleware.
Assigns session ID, logs request timing. No error handling — that's in error_responses.py.
"""
import logging
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

logger = logging.getLogger(__name__)


class RequestLifecycleMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request.state.app_session_id = uuid4()
        start = datetime.now(tz=timezone.utc)

        response = await call_next(request)

        elapsed = (datetime.now(tz=timezone.utc) - start).total_seconds()
        response.headers["X-Process-Time"] = f"{elapsed:.3f}"

        return response
