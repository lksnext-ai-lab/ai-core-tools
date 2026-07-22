"""Unit tests: new User rows for omniadmin emails must get platform_role='admin'
directly, instead of the column default 'viewer'. Also covers promoting an
already-existing user whose email is later added to AICT_OMNIADMINS (JIT
provisioning path, UserRepository.update).

No DB required — the SQLAlchemy session is mocked; we assert on the
constructed/updated User instance's platform_role.
Run with: pytest tests/unit/repositories/test_user_repository_omniadmin_role.py -v
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from repositories.user_repository import UserRepository


class TestCreateSetsPlatformRoleForOmniadmins:

    def test_omniadmin_email_gets_admin_platform_role(self):
        db = MagicMock()
        repo = UserRepository(db)

        with patch("repositories.user_repository.is_omniadmin", return_value=True):
            user = repo.create("admin@example.com", "Admin")

        assert user.platform_role == "admin"

    def test_regular_email_gets_viewer_platform_role(self):
        db = MagicMock()
        repo = UserRepository(db)

        with patch("repositories.user_repository.is_omniadmin", return_value=False):
            user = repo.create("user@example.com", "User")

        assert user.platform_role == "viewer"


class TestUpdatePromotesExistingOmniadmins:

    def test_existing_user_promoted_to_admin_when_email_becomes_omniadmin(self):
        db = MagicMock()
        repo = UserRepository(db)
        user = SimpleNamespace(email="lateomni@example.com", name="Late Omni", platform_role="viewer")

        with patch("repositories.user_repository.is_omniadmin", return_value=True):
            result = repo.update(user)

        assert result.platform_role == "admin"
        db.commit.assert_called_once()

    def test_existing_admin_is_not_recommitted(self):
        """Already-admin omniadmin accounts shouldn't trigger a needless write."""
        db = MagicMock()
        repo = UserRepository(db)
        user = SimpleNamespace(email="admin@example.com", name="Admin", platform_role="admin")

        with patch("repositories.user_repository.is_omniadmin", return_value=True):
            repo.update(user)

        db.commit.assert_not_called()

    def test_regular_user_platform_role_untouched(self):
        db = MagicMock()
        repo = UserRepository(db)
        user = SimpleNamespace(email="user@example.com", name="User", platform_role="viewer")

        with patch("repositories.user_repository.is_omniadmin", return_value=False):
            result = repo.update(user)

        assert result.platform_role == "viewer"
        db.commit.assert_not_called()
