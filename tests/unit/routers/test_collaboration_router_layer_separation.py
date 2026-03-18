from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from routers.internal.collaboration import _build_collaborator_detail_schema, _serialize_user_summary


def test_serialize_user_summary_returns_none_for_missing_user():
    assert _serialize_user_summary(None) is None


def test_build_collaborator_detail_schema_uses_user_service_for_nested_users():
    db = MagicMock()
    collaboration = SimpleNamespace(
        id=5,
        user_id=7,
        role=SimpleNamespace(value="editor"),
        status=SimpleNamespace(value="pending"),
        invited_by=9,
        invited_at=None,
        accepted_at=None,
    )
    invited_user = SimpleNamespace(user_id=7, email="invitee@example.com", name="Invitee")
    inviter_user = SimpleNamespace(user_id=9, email="owner@example.com", name="Owner")

    with patch(
        "routers.internal.collaboration.UserService.get_user_by_id",
        side_effect=[invited_user, inviter_user],
    ) as mock_get_user:
        result = _build_collaborator_detail_schema(db, 42, collaboration)

    assert result.app_id == 42
    assert result.user_id == 7
    assert result.role == "editor"
    assert result.status == "pending"
    assert result.user == {
        "user_id": 7,
        "email": "invitee@example.com",
        "name": "Invitee",
    }
    assert result.inviter == {
        "user_id": 9,
        "email": "owner@example.com",
        "name": "Owner",
    }
    assert mock_get_user.call_args_list == [
        ((db, 7),),
        ((db, 9),),
    ]
