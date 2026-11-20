from datetime import datetime
from unittest.mock import MagicMock

from models.app_collaborator import CollaborationRole, CollaborationStatus
from repositories.admin_user_detail_repository import AdminUserDetailRepository


def test_get_collaborations_returns_selected_membership_fields():
    db = MagicMock()
    invited_at = datetime(2026, 1, 1)
    accepted_at = datetime(2026, 1, 2)
    db.execute.return_value.all.return_value = [
        (
            91,
            17,
            "Example app",
            CollaborationRole.EDITOR,
            CollaborationStatus.ACCEPTED,
            invited_at,
            accepted_at,
            False,
        )
    ]

    collaborations = AdminUserDetailRepository(db).get_collaborations(user_id=8)

    assert len(collaborations) == 1
    assert collaborations[0].collaboration_id == 91
    assert collaborations[0].app_id == 17
    assert collaborations[0].app_name == "Example app"
    assert collaborations[0].role is CollaborationRole.EDITOR
    assert collaborations[0].status is CollaborationStatus.ACCEPTED
    assert collaborations[0].invited_at == invited_at
    assert collaborations[0].accepted_at == accepted_at
    assert collaborations[0].is_frozen is False
