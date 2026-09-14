import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from app.core.logging import get_logger, request_id_ctx

logger = get_logger("app.request")

REQUEST_ID_HEADER = "X-Request-Id"


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Assigns/propagates a correlation ID for every request, per API_STANDARDS.md #6."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        incoming = request.headers.get(REQUEST_ID_HEADER)
        request_id = incoming if incoming else f"req_{uuid.uuid4().hex}"
        token = request_id_ctx.set(request_id)
        start = time.perf_counter()
        try:
            try:
                response = await call_next(request)
            except Exception:
                duration_ms = round((time.perf_counter() - start) * 1000, 2)
                logger.exception(
                    "request_failed",
                    extra={"extra_fields": {"path": request.url.path, "method": request.method, "duration_ms": duration_ms}},
                )
                raise
            duration_ms = round((time.perf_counter() - start) * 1000, 2)
            response.headers[REQUEST_ID_HEADER] = request_id
            logger.info(
                "request_completed",
                extra={
                    "extra_fields": {
                        "path": request.url.path,
                        "method": request.method,
                        "status_code": response.status_code,
                        "duration_ms": duration_ms,
                    }
                },
            )
            return response
        finally:
            request_id_ctx.reset(token)
