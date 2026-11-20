from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from models.app_collaborator import CollaborationRole, CollaborationStatus
from services.app_collaboration_service import AppCollaborationService


def _service(collaboration):
    service = AppCollaborationService(MagicMock())
    service.repo = MagicMock()
    service.repo.get_collaboration_by_id.return_value = collaboration
    return service


@pytest.mark.parametrize(
    ("action", "expected_status"),
    [
        ("accept", CollaborationStatus.ACCEPTED),
        ("decline", CollaborationStatus.DECLINED),
    ],
)
def test_respond_to_regular_invitation_updates_status(action, expected_status):
    collaboration = SimpleNamespace(
        user_id=12,
        role=CollaborationRole.EDITOR,
        status=CollaborationStatus.PENDING,
    )
    service = _service(collaboration)

    assert service.respond_to_invitation(34, 12, action) is True

    update = service.repo.update_collaboration.call_args.args[1]
    assert update["status"] is expected_status
    assert ("accepted_at" in update) is (action == "accept")


def test_respond_to_invitation_rejects_another_users_invitation():
    service = _service(
        SimpleNamespace(
            user_id=12,
            role=CollaborationRole.EDITOR,
            status=CollaborationStatus.PENDING,
        )
    )

    assert service.respond_to_invitation(34, 99, "accept") is False
    service.repo.update_collaboration.assert_not_called()


@pytest.mark.parametrize("action", ["accept", "decline"])
def test_respond_to_ownership_offer_delegates_to_ownership_service(action, mocker):
    collaboration = SimpleNamespace(
        user_id=12,
        role=CollaborationRole.OWNER,
        status=CollaborationStatus.PENDING,
    )
    service = _service(collaboration)
    operation = mocker.patch(
        f"services.app_ownership_service.AppOwnershipService.{action}"
    )

    assert service.respond_to_invitation(34, 12, action) is True
    operation.assert_called_once_with(service.db, 34, actor_user_id=12)


def test_invalid_ownership_offer_action_does_not_invoke_transfer(mocker):
    collaboration = SimpleNamespace(
        user_id=12,
        role=CollaborationRole.OWNER,
        status=CollaborationStatus.PENDING,
    )
    service = _service(collaboration)
    accept = mocker.patch("services.app_ownership_service.AppOwnershipService.accept")
    decline = mocker.patch("services.app_ownership_service.AppOwnershipService.decline")

    assert service.respond_to_invitation(34, 12, "cancel") is False
    accept.assert_not_called()
    decline.assert_not_called()
