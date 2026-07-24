"""Unit tests: inviting an omniadmin must not be blocked by the
viewer-platform-role restriction. Omniadmin accounts created before the
platform_role='admin' default existed may still carry the old 'viewer'
value, which shouldn't force a viewer-only app-role invite.

No DB required — services are mocked.
Run with: pytest tests/unit/routers/test_collaboration_omniadmin_invite.py -v
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from routers.internal.collaboration import invite_collaborator
from schemas.apps_schemas import InviteCollaboratorSchema
from routers.controls.role_authorization import AppRole


def _auth_context(user_id=99, email="owner@example.com"):
    return SimpleNamespace(identity=SimpleNamespace(id=user_id, email=email))


def _target_user(email, platform_role="viewer"):
    return SimpleNamespace(user_id=1, email=email, name="Target", platform_role=platform_role)


async def _invoke(email, role, is_omniadmin_value):
    db = MagicMock()
    collaboration_service = MagicMock()
    collaboration_service.can_user_administer_app.return_value = True
    collaboration_service.invite_user_to_app.return_value = SimpleNamespace(id=1)

    with patch("routers.internal.collaboration.get_services", return_value=(MagicMock(), collaboration_service)), \
            patch("routers.internal.collaboration.UserService.get_user_by_email", return_value=_target_user(email)), \
            patch("routers.internal.collaboration.is_omniadmin", return_value=is_omniadmin_value), \
            patch("routers.internal.collaboration._build_collaborator_detail_schema", return_value=SimpleNamespace()):
        return await invite_collaborator(
            app_id=1,
            invitation_data=InviteCollaboratorSchema(email=email, role=role),
            auth_context=_auth_context(),
            db=db,
            role=AppRole.OWNER,
        )


class TestOmniadminInviteExemption:

    @pytest.mark.asyncio
    async def test_omniadmin_can_be_invited_with_non_viewer_role(self):
        result = await _invoke("admin@example.com", "administrator", is_omniadmin_value=True)
        assert result is not None

    @pytest.mark.asyncio
    async def test_regular_viewer_platform_user_still_locked_to_viewer_role(self):
        with pytest.raises(HTTPException) as exc_info:
            await _invoke("user@example.com", "administrator", is_omniadmin_value=False)

        assert exc_info.value.status_code == 400
        assert "viewer" in exc_info.value.detail.lower()
