"""Neutralise untrusted values before they are written to logs (log injection, CWE-117)."""

from typing import Any

_MAX_LEN = 500


def sanitize_for_log(value: Any) -> str:
    """Return ``value`` as a single log-safe line.

    CR/LF are replaced so a caller-supplied value cannot forge extra log
    lines, other control characters are escaped, and the result is capped.
    """
    text = str(value).replace("\r", "\\r").replace("\n", "\\n")
    text = "".join(ch if ch.isprintable() else f"\\x{ord(ch):02x}" for ch in text)
    return text if len(text) <= _MAX_LEN else text[:_MAX_LEN] + "…"
