"""Unit tests: administrator-role collaborators (not just the app owner) must
be able to invite new collaborators to an app.

Regression: invite_collaborator's dependency already accepted ADMINISTRATOR
via require_min_role("administrator"), but a redundant manual check right
after re-restricted to owner-only (can_user_manage_app), so administrators
got a confusing 403 despite passing the route's own permission gate.

No DB required — services are mocked.
Run with: pytest tests/unit/routers/test_collaboration_administrator_can_invite.py -v
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from routers.internal.collaboration import invite_collaborator
from schemas.apps_schemas import InviteCollaboratorSchema
from routers.controls.role_authorization import AppRole


def _auth_context(user_id=42, email="administrator@example.com"):
    return SimpleNamespace(identity=SimpleNamespace(id=user_id, email=email))


def _target_user(email, platform_role="editor"):
    return SimpleNamespace(user_id=7, email=email, name="Invitee", platform_role=platform_role)


async def _invoke(can_administer: bool):
    db = MagicMock()
    collaboration_service = MagicMock()
    collaboration_service.can_user_administer_app.return_value = can_administer
    collaboration_service.invite_user_to_app.return_value = SimpleNamespace(id=1)

    with patch("routers.internal.collaboration.get_services", return_value=(MagicMock(), collaboration_service)), \
            patch("routers.internal.collaboration.UserService.get_user_by_email", return_value=_target_user("invitee@example.com")), \
            patch("routers.internal.collaboration.is_omniadmin", return_value=False), \
            patch("routers.internal.collaboration._build_collaborator_detail_schema", return_value=SimpleNamespace()):
        return await invite_collaborator(
            app_id=1,
            invitation_data=InviteCollaboratorSchema(email="invitee@example.com", role="editor"),
            auth_context=_auth_context(),
            db=db,
            role=AppRole.ADMINISTRATOR,
        )


class TestAdministratorCanInvite:

    @pytest.mark.asyncio
    async def test_administrator_collaborator_can_invite(self):
        """can_user_administer_app=True (owner OR administrator collaborator) must be accepted."""
        result = await _invoke(can_administer=True)
        assert result is not None

    @pytest.mark.asyncio
    async def test_non_administrator_still_gets_403(self):
        with pytest.raises(HTTPException) as exc_info:
            await _invoke(can_administer=False)

        assert exc_info.value.status_code == 403
        assert "administrator" in exc_info.value.detail.lower()
