"""Machine-readable failures shared by public place discovery services."""

import math
import time
from email.utils import parsedate_to_datetime
from typing import Any

import httpx


class DiscoveryError(ValueError):
    def __init__(
        self,
        message: str,
        code: str,
        *,
        retryable: bool = False,
        retry_after_seconds: float | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.retryable = retryable
        self.retry_after_seconds = retry_after_seconds


def retry_after(value: str | None, now: float) -> float | None:
    if not value:
        return None
    try:
        seconds = float(value)
    except ValueError:
        try:
            seconds = parsedate_to_datetime(value).timestamp() - now
        except (ValueError, TypeError, OverflowError):
            return None
    return max(0.0, seconds) if math.isfinite(seconds) else None


def failure(exc: Exception, message: str) -> dict[str, Any]:
    if isinstance(exc, DiscoveryError):
        code, retryable, delay = exc.code, exc.retryable, exc.retry_after_seconds
    elif isinstance(exc, (httpx.TransportError, TimeoutError)):
        code, retryable, delay = "upstream_timeout", True, None
    elif isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        code = "rate_limited" if status == 429 else "upstream_http_error"
        retryable = status == 429 or status >= 500
        delay = retry_after(exc.response.headers.get("Retry-After"), time.time())
    elif isinstance(exc, ValueError):
        code, retryable, delay = "invalid_arguments", False, None
    else:
        code, retryable, delay = "invalid_upstream_response", False, None
    # Do not include complete request URLs or upstream response bodies.
    detail = str(exc) if isinstance(exc, ValueError) else code.replace("_", " ")
    return {
        "success": False,
        "message": message,
        "error": detail,
        "error_details": {
            "code": code,
            "retryable": retryable,
            "retry_after_seconds": delay,
        },
    }
