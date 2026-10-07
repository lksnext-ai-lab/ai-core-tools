from datetime import datetime
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from models.api_key import APIKey
from repositories.api_key_repository import APIKeyRepository


class PublicAuthService:
    """Business logic for public API key authentication."""

    def __init__(self, api_key_repository: APIKeyRepository | None = None):
        self.api_key_repository = api_key_repository or APIKeyRepository()

    def _fetch_active_key(self, db: Session, app_id: int, api_key: str) -> Optional[APIKey]:
        """The one repository call both public entry points use: an active key
        scoped to `app_id`. Split out from `_owner_is_active` so neither public
        method pays for a second DB round trip to re-derive the same row."""
        return self.api_key_repository.get_active_by_app_and_key(db, app_id, api_key)

    @staticmethod
    def _owner_is_active(api_key_obj: APIKey) -> bool:
        """True unless `api_key_obj`'s app has an owner and that owner is deactivated.

        `get_active_by_app_and_key` already `joinedload`s `app.owner`, so this
        never triggers a lazy load -- it is a pure in-memory check on the row
        `_fetch_active_key` already returned.
        """
        app_owner = api_key_obj.app.owner if api_key_obj.app else None
        return not (app_owner and hasattr(app_owner, "is_active") and not app_owner.is_active)

    def _lookup_active_key(self, db: Session, app_id: int, api_key: str) -> Optional[APIKey]:
        """The shared, non-raising predicate: active key + active owner, scoped to `app_id`.

        One source of truth for "is this key currently usable for this app",
        built from the same two primitives (`_fetch_active_key`,
        `_owner_is_active`) that `validate_api_key_for_app` uses directly (to
        keep its distinct 401-vs-403 status codes and its single DB round
        trip) -- review round 2, MEDIUM-1: the active/owner-active predicate
        itself is defined exactly once, here and in `validate_api_key_for_app`,
        never forked.

        Returns:
            The matching `APIKey` row, or `None` if it does not exist, is
            inactive, belongs to another app, or its app's owner account is
            deactivated. Never raises and never writes to the DB.
        """
        api_key_obj = self._fetch_active_key(db, app_id, api_key)
        if api_key_obj is None or not self._owner_is_active(api_key_obj):
            return None
        return api_key_obj

    def validate_api_key_for_app(self, db: Session, app_id: int, api_key: str) -> APIKey:
        """
        Validate API key for a specific app and update usage metadata.

        Args:
            db: Database session
            app_id: The app ID to validate against
            api_key: The API key value

        Returns:
            The validated API key ORM object

        Raises:
            HTTPException: If authentication fails
        """
        api_key_obj = self._fetch_active_key(db, app_id, api_key)

        if not api_key_obj:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or inactive API key for this app",
            )

        if not self._owner_is_active(api_key_obj):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="This API key belongs to a deactivated account",
            )

        self.api_key_repository.update_last_used_at(db, api_key_obj, datetime.now())
        return api_key_obj

    def find_valid_key_for_app(self, db: Session, app_id: int, api_key: str) -> Optional[APIKey]:
        """Non-raising counterpart of `validate_api_key_for_app` (A2A visibility, step_011).

        Delegates to `_lookup_active_key` -- the exact same predicate
        `validate_api_key_for_app` is built from -- but returns `None`
        instead of raising, and never touches `last_used_at` (visibility
        resolution must stay side-effect-free: NFR-2, and FR-10's
        uniform-404/401 semantics must not depend on whether this call
        happened to "use" the key).

        Args:
            db: Database session.
            app_id: The app id the key must belong to.
            api_key: The raw key value presented by the caller.

        Returns:
            The matching, active `APIKey` row, or `None` if it does not
            exist, is inactive, belongs to another app, or its app's owner
            account is deactivated.
        """
        return self._lookup_active_key(db, app_id, api_key)
