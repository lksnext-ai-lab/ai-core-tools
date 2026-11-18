from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from models.app_collaborator import CollaborationRole, CollaborationStatus
from services.app_collaboration_service import AppCollaborationService


def _service_with_invitation(role: CollaborationRole) -> AppCollaborationService:
    service = AppCollaborationService(MagicMock())
    service.repo = MagicMock()
    service.repo.get_collaboration_by_id.return_value = SimpleNamespace(
        user_id=12,
        role=role,
        status=CollaborationStatus.PENDING,
    )
    return service


@pytest.mark.parametrize(
    ("action", "method_name"),
    [("accept", "accept"), ("decline", "decline")],
)
def test_respond_to_owner_offer_delegates_to_ownership_service(action, method_name):
    service = _service_with_invitation(CollaborationRole.OWNER)

    with patch(
        f"services.app_ownership_service.AppOwnershipService.{method_name}"
    ) as ownership_action:
        result = service.respond_to_invitation(8, 12, action)

    assert result is True
    ownership_action.assert_called_once_with(
        service.db, 8, actor_user_id=12
    )
    service.repo.update_collaboration.assert_not_called()


@pytest.mark.parametrize(
    ("action", "expected_status"),
    [
        ("accept", CollaborationStatus.ACCEPTED),
        ("decline", CollaborationStatus.DECLINED),
    ],
)
def test_respond_to_regular_invitation_updates_status(action, expected_status):
    service = _service_with_invitation(CollaborationRole.EDITOR)
    collaboration = service.repo.get_collaboration_by_id.return_value

    result = service.respond_to_invitation(8, 12, action)

    assert result is True
    updated_collaboration, update_data = service.repo.update_collaboration.call_args.args
    assert updated_collaboration is collaboration
    assert update_data["status"] == expected_status
    if action == "accept":
        assert isinstance(update_data["accepted_at"], datetime)
    else:
        assert "accepted_at" not in update_data
