"""Delivery errors shared by every outbound provider."""


class DeliveryError(Exception):
    def __init__(self, message: str, *, kind: str = "permanent", http_status: int | None = None, retry_after: float | None = None):
        super().__init__(message)
        self.kind = kind
        self.http_status = http_status
        self.retry_after = retry_after
