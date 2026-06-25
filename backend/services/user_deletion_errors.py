"""Typed domain exceptions for user-deletion orchestration.

Plain Python exceptions — no FastAPI dependency. Router layer maps to HTTP status codes:
UserNotFoundError → 404, SelfDeletionError → 400, OmniadminDeletionError → 403,
OwnedAppsPresentError → 409.
"""
from __future__ import annotations

from typing import List, TypedDict


class OwnedAppSummary(TypedDict):
    """Minimal app descriptor returned in the 409 owned-apps payload."""

    app_id: int
    name: str


class UserDeletionError(Exception):
    """Base class for all user-deletion domain errors."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message

    def __str__(self) -> str:
        return self.message


class UserNotFoundError(UserDeletionError):
    """Target user_id does not exist (→ 404)."""

    def __init__(self, user_id: int) -> None:
        super().__init__(f"User {user_id} not found.")
        self.user_id = user_id


class SelfDeletionError(UserDeletionError):
    """Administrator attempted to delete their own account (→ 400)."""

    def __init__(self, user_id: int) -> None:
        super().__init__("An administrator cannot delete their own account.")
        self.user_id = user_id


class OmniadminDeletionError(UserDeletionError):
    """Target user is an omniadmin and therefore undeletable (→ 403).

    ``email`` is stored for structured logging only — never forward to API responses.
    """

    def __init__(self, email: str) -> None:
        super().__init__("Cannot delete an administrator account.")
        self.email = email


class OwnedAppsPresentError(UserDeletionError):
    """User owns apps and mode is 'block' (→ 409).

    ``owned_apps`` is included in the 409 response body so the caller can present
    a transfer/cascade dialog.
    """

    def __init__(self, owned_apps: List[OwnedAppSummary]) -> None:
        count = len(owned_apps)
        super().__init__(
            f"User owns {count} app(s). Choose 'cascade_apps' to delete them "
            "or 'transfer_apps' to reassign ownership before deleting the user."
        )
        self.owned_apps: List[OwnedAppSummary] = owned_apps
