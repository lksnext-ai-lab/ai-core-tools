"""Delivery errors shared by every outbound provider."""

from typing import Literal

DeliveryErrorKind = Literal["permanent", "retryable", "unknown"]


class DeliveryError(Exception):
    def __init__(
        self, message: str, *, kind: DeliveryErrorKind = "permanent",
        http_status: int | None = None, retry_after: float | None = None,
    ):
        super().__init__(message)
        self.kind = kind
        self.http_status = http_status
        self.retry_after = retry_after


class ProviderNotFoundError(ValueError):
    """Raised when a provider key is not registered."""

    def __init__(self, key: str):
        super().__init__(f"Unsupported output provider: {key}")
        self.key = key
