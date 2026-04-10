"""Middleware for request/response processing and context management."""

import uuid
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
import structlog

logger = structlog.get_logger()


class LoggingContextMiddleware(BaseHTTPMiddleware):
    """Middleware to bind request-level context (request_id, client info) to structured logs."""

    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = str(uuid.uuid4())
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(
            request_id=request_id,
            method=request.method,
            path=request.url.path,
            client_host=request.client.host if request.client else "unknown",
        )

        try:
            response = await call_next(request)
            response.headers["X-Request-ID"] = request_id
            return response
        except Exception as e:
            logger.exception(
                "request_failed",
                path=request.url.path,
                error=str(e),
            )
            raise
