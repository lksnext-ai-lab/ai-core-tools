from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from sqlalchemy.exc import IntegrityError

from models.app_collaborator import CollaborationRole, CollaborationStatus
from services.admin_user_detail_service import AdminUserDetailService
from services.api_key_service import APIKeyService
from services.app_collaboration_service import AppCollaborationService


def test_direct_app_grant_creates_accepted_collaboration(mocker):
    repo = MagicMock()
    repo.get_user_by_id.return_value = SimpleNamespace(user_id=12, platform_role="editor")
    repo.get_membership_by_app_and_user.return_value = None
    app_repository = mocker.patch(
        "services.app_collaboration_service.AppRepository"
    )
    app_repository.return_value.get_by_id.return_value = SimpleNamespace(owner_id=7)
    service = AppCollaborationService(MagicMock())
    service.repo = repo

    service.grant_access_directly(34, 12, "administrator", 1)

    created = repo.create_collaboration.call_args.args[0]
    assert created["role"] is CollaborationRole.ADMINISTRATOR
    assert created["status"] is CollaborationStatus.ACCEPTED
    assert created["accepted_at"] is not None
    assert created["invited_by"] == 1


def test_direct_app_grant_rejects_editor_role_for_platform_viewer(mocker):
    repo = MagicMock()
    repo.get_user_by_id.return_value = SimpleNamespace(user_id=12, platform_role="viewer")
    app_repository = mocker.patch("services.app_collaboration_service.AppRepository")
    app_repository.return_value.get_by_id.return_value = SimpleNamespace(owner_id=7)
    service = AppCollaborationService(MagicMock())
    service.repo = repo

    with pytest.raises(ValueError, match="viewer platform role"):
        service.grant_access_directly(34, 12, "editor", 1)

    repo.create_collaboration.assert_not_called()
    repo.update_collaboration.assert_not_called()


def test_direct_app_grant_recovers_from_concurrent_insert(mocker):
    db = MagicMock()
    repo = MagicMock()
    target_user = SimpleNamespace(user_id=12, platform_role="editor")
    existing = SimpleNamespace(role=CollaborationRole.VIEWER)
    repo.get_user_by_id.return_value = target_user
    repo.get_membership_by_app_and_user.side_effect = [None, existing]
    repo.create_collaboration.side_effect = IntegrityError(
        "insert", {}, Exception("duplicate membership")
    )
    repo.update_collaboration.return_value = existing
    app_repository = mocker.patch("services.app_collaboration_service.AppRepository")
    app_repository.return_value.get_by_id.return_value = SimpleNamespace(owner_id=7)
    service = AppCollaborationService(db)
    service.repo = repo

    result = service.grant_access_directly(34, 12, "administrator", 1)

    assert result is existing
    db.rollback.assert_called_once()
    repo.update_collaboration.assert_called_once()


def test_direct_app_grant_does_not_change_owner(mocker):
    repo = MagicMock()
    repo.get_user_by_id.return_value = SimpleNamespace(user_id=12, platform_role="editor")
    app_repository = mocker.patch(
        "services.app_collaboration_service.AppRepository"
    )
    app_repository.return_value.get_by_id.return_value = SimpleNamespace(owner_id=12)
    service = AppCollaborationService(MagicMock())
    service.repo = repo

    try:
        service.grant_access_directly(34, 12, "editor", 1)
    except ValueError as exc:
        assert "app owner" in str(exc)
    else:
        raise AssertionError("Expected ownership changes to be rejected")

    repo.create_collaboration.assert_not_called()
    repo.update_collaboration.assert_not_called()


def test_admin_cannot_manage_own_account(mocker):
    user = SimpleNamespace(user_id=12, email="admin@example.com")
    repository = mocker.patch(
        "services.admin_user_detail_service.AdminUserDetailRepository"
    )
    repository.return_value.get_user.return_value = user

    with pytest.raises(ValueError, match="own account"):
        AdminUserDetailService.get_manageable_user(MagicMock(), 12, 12)


def test_admin_cannot_manage_omniadmin_account(mocker):
    user = SimpleNamespace(user_id=12, email="protected@example.com")
    repository = mocker.patch(
        "services.admin_user_detail_service.AdminUserDetailRepository"
    )
    repository.return_value.get_user.return_value = user
    mocker.patch("services.admin_user_detail_service.is_omniadmin", return_value=True)

    with pytest.raises(ValueError, match="Omniadmin"):
        AdminUserDetailService.get_manageable_user(MagicMock(), 12, 1)


def test_admin_api_key_status_is_explicit_and_user_scoped():
    db = MagicMock()
    repository = MagicMock()
    key = SimpleNamespace(is_active=True)
    repository.get_by_id_and_user.return_value = key
    repository.update.return_value = key

    result = APIKeyService(repository).set_status_for_user(
        db,
        user_id=12,
        key_id=56,
        is_active=False,
    )

    assert result is False
    assert key.is_active is False
    repository.get_by_id_and_user.assert_called_once_with(db, 56, 12)
    repository.update.assert_called_once_with(db, key)
