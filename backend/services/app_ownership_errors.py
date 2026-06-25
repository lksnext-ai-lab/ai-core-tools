"""Typed domain exceptions for app ownership transfer.

Plain Python exceptions — no FastAPI dependency. Router layer maps to HTTP status codes:
AppNotFoundError → 404, TransferRecipientInvalidError → 400, TierLimitExceededError → 409,
OwnershipOfferNotFoundError → 404, NotOfferRecipientError → 403.
"""
from __future__ import annotations


class AppOwnershipError(Exception):
    """Base class for all app-ownership-transfer domain errors."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message

    def __str__(self) -> str:
        return self.message


class AppNotFoundError(AppOwnershipError):
    """Target app_id does not exist (→ 404)."""

    def __init__(self, app_id: int) -> None:
        super().__init__(f"App {app_id} not found.")
        self.app_id = app_id


class TransferRecipientInvalidError(AppOwnershipError):
    """Proposed new owner failed validation: non-existent, inactive, or already owner (→ 400)."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class TierLimitExceededError(AppOwnershipError):
    """Transfer would push the recipient over their SaaS app-count limit (→ 409)."""

    def __init__(self, user_id: int, detail: str = "") -> None:
        msg = f"Transfer would exceed the app limit for user {user_id}."
        if detail:
            msg = f"{msg} {detail}"
        super().__init__(msg)
        self.user_id = user_id
        self.detail = detail


class OwnershipOfferNotFoundError(AppOwnershipError):
    """Pending OWNER offer (AppCollaborator row) not found (→ 404)."""

    def __init__(
        self,
        collaboration_id: int | None = None,
        app_id: int | None = None,
    ) -> None:
        if collaboration_id is not None:
            msg = f"Ownership offer {collaboration_id} not found."
        elif app_id is not None:
            msg = f"No pending ownership offer found for app {app_id}."
        else:
            msg = "Ownership offer not found."
        super().__init__(msg)
        self.collaboration_id = collaboration_id
        self.app_id = app_id


class NotOfferRecipientError(AppOwnershipError):
    """Actor attempted to accept/decline an offer not addressed to them (→ 403)."""

    def __init__(self, actor_user_id: int, collaboration_id: int) -> None:
        super().__init__(
            f"User {actor_user_id} is not the recipient of ownership offer {collaboration_id}."
        )
        self.actor_user_id = actor_user_id
        self.collaboration_id = collaboration_id
