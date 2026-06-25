"""Unit tests for user_deletion_errors and app_ownership_errors typed exceptions.

No DB required — these are plain Python exceptions.
Run with: pytest tests/unit/services/test_user_deletion_errors.py -v
"""

import pytest


class TestUserDeletionErrors:

    def test_user_not_found_error_message(self):
        from services.user_deletion_errors import UserNotFoundError

        exc = UserNotFoundError(42)
        assert "42" in str(exc)
        assert exc.user_id == 42

    def test_self_deletion_error_message(self):
        from services.user_deletion_errors import SelfDeletionError

        exc = SelfDeletionError(7)
        assert "administrator" in str(exc).lower()
        assert exc.user_id == 7

    def test_omniadmin_deletion_error_message(self):
        from services.user_deletion_errors import OmniadminDeletionError

        exc = OmniadminDeletionError("admin@example.com")
        # The public message must NOT include the email (security: never leak admin email to caller)
        assert "admin@example.com" not in str(exc)
        assert "administrator" in str(exc).lower()
        assert exc.email == "admin@example.com"

    def test_owned_apps_present_error_carries_summaries(self):
        from services.user_deletion_errors import OwnedAppsPresentError

        summaries = [{"app_id": 1, "name": "Workspace A"}, {"app_id": 2, "name": "Workspace B"}]
        exc = OwnedAppsPresentError(summaries)
        assert exc.owned_apps == summaries
        assert "2" in str(exc)  # count of apps mentioned in message

    def test_owned_apps_present_error_is_409_candidate(self):
        """OwnedAppsPresentError must be a subclass of UserDeletionError."""
        from services.user_deletion_errors import OwnedAppsPresentError, UserDeletionError

        exc = OwnedAppsPresentError([])
        assert isinstance(exc, UserDeletionError)

    def test_all_errors_are_subclasses_of_user_deletion_error(self):
        from services.user_deletion_errors import (
            UserDeletionError,
            UserNotFoundError,
            SelfDeletionError,
            OmniadminDeletionError,
            OwnedAppsPresentError,
        )

        for cls in [UserNotFoundError, SelfDeletionError, OmniadminDeletionError, OwnedAppsPresentError]:
            assert issubclass(cls, UserDeletionError), f"{cls.__name__} must subclass UserDeletionError"


class TestAppOwnershipErrors:

    def test_app_not_found_error(self):
        from services.app_ownership_errors import AppNotFoundError

        exc = AppNotFoundError(99)
        assert "99" in str(exc)
        assert exc.app_id == 99

    def test_transfer_recipient_invalid_error(self):
        from services.app_ownership_errors import TransferRecipientInvalidError

        exc = TransferRecipientInvalidError("User is inactive.")
        assert "inactive" in str(exc)
        assert exc.reason == "User is inactive."

    def test_tier_limit_exceeded_error(self):
        from services.app_ownership_errors import TierLimitExceededError

        exc = TierLimitExceededError(user_id=5, detail="Free tier allows 1 app.")
        assert "5" in str(exc)
        assert "Free tier" in str(exc)
        assert exc.user_id == 5

    def test_all_errors_are_subclasses_of_app_ownership_error(self):
        from services.app_ownership_errors import (
            AppOwnershipError,
            AppNotFoundError,
            TransferRecipientInvalidError,
            TierLimitExceededError,
        )

        for cls in [AppNotFoundError, TransferRecipientInvalidError, TierLimitExceededError]:
            assert issubclass(cls, AppOwnershipError), f"{cls.__name__} must subclass AppOwnershipError"
