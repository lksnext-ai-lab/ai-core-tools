"""Unit tests: omniadmins must be searchable/invitable via UserService.search_users.

No DB required — UserRepository is mocked.
Run with: pytest tests/unit/services/test_user_service_omniadmin_search.py -v
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from services.user_service import UserService


def _fake_user(user_id, email, name, platform_role="viewer"):
    return SimpleNamespace(
        user_id=user_id,
        email=email,
        name=name,
        create_date=None,
        owned_apps=[],
        api_keys=[],
        is_active=True,
        platform_role=platform_role,
    )


class TestSearchUsersIncludesOmniadmins:

    def test_search_users_does_not_exclude_omniadmins(self):
        """search_users must not exclude any emails — omniadmins show up as protected accounts."""
        db = MagicMock()
        omniadmin = _fake_user(1, "admin@example.com", "Admin")

        with patch("services.user_service.UserRepository") as MockRepo:
            instance = MockRepo.return_value
            instance.search_users.return_value = ([omniadmin], 1)

            users, total = UserService.search_users(db, "admin")

            instance.search_users.assert_called_once_with("admin", 1, 10)
            assert total == 1
            assert users[0]["email"] == "admin@example.com"

    def test_search_users_marks_omniadmin_flag(self):
        db = MagicMock()
        omniadmin = _fake_user(1, "admin@example.com", "Admin")
        regular = _fake_user(2, "user@example.com", "User")

        with patch("services.user_service.UserRepository") as MockRepo, \
                patch("services.user_service.is_omniadmin", side_effect=lambda email: email == "admin@example.com"):
            instance = MockRepo.return_value
            instance.search_users.return_value = ([omniadmin, regular], 2)

            users, _ = UserService.search_users(db, "a")

            by_email = {u["email"]: u for u in users}
            assert by_email["admin@example.com"]["is_omniadmin"] is True
            assert by_email["user@example.com"]["is_omniadmin"] is False


class TestGetAllUsersIncludesOmniadmins:

    def test_get_all_users_does_not_exclude_omniadmins(self):
        """The general admin user-management list must not exclude any emails —
        omniadmins show up as protected accounts, not hidden entirely."""
        db = MagicMock()
        omniadmin = _fake_user(1, "admin@example.com", "Admin")

        with patch("services.user_service.UserRepository") as MockRepo, \
                patch("services.user_service.is_omniadmin", return_value=True):
            instance = MockRepo.return_value
            instance.get_all_paginated.return_value = ([omniadmin], 1)

            users, total = UserService.get_all_users(db)

            instance.get_all_paginated.assert_called_once_with(1, 10)
            assert total == 1
            assert users[0]["email"] == "admin@example.com"
            assert users[0]["is_omniadmin"] is True
