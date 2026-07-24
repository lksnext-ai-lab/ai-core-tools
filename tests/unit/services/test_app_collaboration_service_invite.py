"""Unit tests: AppCollaborationService.invite_user_to_app's actor-permission
check must accept administrator-role collaborators, not just the app owner.

No DB required — the repository is mocked.
Run with: pytest tests/unit/services/test_app_collaboration_service_invite.py -v
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from services.app_collaboration_service import AppCollaborationService


def _service_with_mock_repo():
    db = MagicMock()
    service = AppCollaborationService(db)
    service.repo = MagicMock()
    return service


class TestInviteUserToAppActorPermission:

    def test_administrator_collaborator_can_invite(self):
        service = _service_with_mock_repo()
        service.repo.can_user_administer_app.return_value = True
        service.repo.get_user_by_email.return_value = SimpleNamespace(user_id=7)
        service.repo.can_user_manage_app.return_value = False  # invitee is not the owner
        service.repo.get_collaboration_by_app_and_user.return_value = None
        service.repo.create_collaboration.return_value = SimpleNamespace(id=1)

        with patch("services.tier_enforcement_service.TierEnforcementService"):
            result = service.invite_user_to_app(
                app_id=1, user_email="invitee@example.com", invited_by_user_id=42, role="editor"
            )

        assert result is not None
        service.repo.can_user_administer_app.assert_called_once_with(42, 1)

    def test_non_administrator_actor_is_rejected(self):
        service = _service_with_mock_repo()
        service.repo.can_user_administer_app.return_value = False

        with pytest.raises(ValueError, match="owners or administrators"):
            service.invite_user_to_app(
                app_id=1, user_email="invitee@example.com", invited_by_user_id=42, role="editor"
            )

    def test_target_ownership_check_still_uses_strict_owner_only_lookup(self):
        """Regression guard: the 'cannot invite the app owner' check must stay
        on can_user_manage_app (strict ownership), not the administrator-inclusive
        can_user_administer_app — otherwise inviting an admin-role collaborator's
        email a second time would be wrongly rejected as 'is the owner'."""
        service = _service_with_mock_repo()
        service.repo.can_user_administer_app.return_value = True
        service.repo.get_user_by_email.return_value = SimpleNamespace(user_id=7)
        service.repo.can_user_manage_app.return_value = True  # invitee IS the owner

        with pytest.raises(ValueError, match="Cannot invite the app owner"):
            service.invite_user_to_app(
                app_id=1, user_email="owner@example.com", invited_by_user_id=42, role="editor"
            )

        service.repo.can_user_manage_app.assert_called_once_with(7, 1)
