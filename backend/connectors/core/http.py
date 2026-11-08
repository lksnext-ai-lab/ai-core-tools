"""HTTP helpers shared by outbound providers (SSRF host check, Retry-After, log redaction)."""

import logging
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

from utils.ssrf_guard import is_blocked_ip, resolve_host


class _RedactHttpxRequestUrls(logging.Filter):
    """Prevent HTTPX's INFO request log from exposing webhook credentials."""

    def filter(self, record: logging.LogRecord) -> bool:
        if record.name == "httpx" and "HTTP Request:" in str(record.msg):
            record.msg = "HTTP request completed (URL redacted)"
            record.args = ()
        return True


def install_httpx_redaction() -> None:
    """Attach the URL-redaction filter to the ``httpx`` logger once (idempotent)."""
    httpx_logger = logging.getLogger("httpx")
    if not any(isinstance(existing, _RedactHttpxRequestUrls) for existing in httpx_logger.filters):
        httpx_logger.addFilter(_RedactHttpxRequestUrls())


def ensure_public_host(hostname: str, label: str) -> None:
    """Reject hosts that do not resolve or resolve to a non-public address (SSRF guard)."""
    try:
        addresses = resolve_host(hostname)
    except OSError as exc:
        raise ValueError(f"{label} host could not be resolved") from exc
    if not addresses:
        raise ValueError(f"{label} host could not be resolved")
    if any(is_blocked_ip(address) for address in addresses):
        raise ValueError(f"{label} URL cannot target a private or reserved network")


def parse_retry_after(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        try:
            target = parsedate_to_datetime(value)
            if target.tzinfo is None:
                target = target.replace(tzinfo=timezone.utc)
            return max(0.0, (target - datetime.now(timezone.utc)).total_seconds())
        except (TypeError, ValueError, OverflowError):
            return None


install_httpx_redaction()
