from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from models.group_app_access_rule import GroupAppAccessRole
from services.group_app_access_service import (
    GroupAppAccessForbiddenError,
    GroupAppAccessInvalidRoleError,
    GroupAppAccessNotFoundError,
    GroupAppAccessService,
)


def _service(db=None):
    service = GroupAppAccessService(db or MagicMock())
    service.repository = MagicMock()
    return service


class TestGroupAppAccessManagerAuthorization:
    def test_owner_or_app_admin_check_is_required_before_identity_lookup(self):
        db = MagicMock()
        service = _service(db)

        with patch(
            "services.group_app_access_service.AppCollaborationRepository"
        ) as collaboration_repository:
            collaboration_repository.return_value.can_user_administer_app.return_value = False

            with pytest.raises(GroupAppAccessForbiddenError):
                service.list_rules(app_id=12, user_id=31)

        collaboration_repository.return_value.can_user_administer_app.assert_called_once_with(
            31, 12
        )
        service.repository.get_identity.assert_not_called()

    def test_accepted_app_manager_is_authorized(self):
        service = _service()

        with patch(
            "services.group_app_access_service.AppCollaborationRepository"
        ) as collaboration_repository:
            collaboration_repository.return_value.can_user_administer_app.return_value = True
            service.authorize_manager(app_id=12, user_id=31)

        collaboration_repository.return_value.can_user_administer_app.assert_called_once_with(
            31, 12
        )


class TestGroupAppAccessConnectionScope:
    def test_rule_listing_is_scoped_to_managers_linked_connection(self):
        service = _service()
        service.repository.get_identity.return_value = SimpleNamespace(connection_id=44)
        service.repository.list_for_connection.return_value = []

        with patch(
            "services.group_app_access_service.AppCollaborationRepository"
        ) as collaboration_repository:
            collaboration_repository.return_value.can_user_administer_app.return_value = True
            result = service.list_rules(app_id=12, user_id=31, offset=10, limit=7)

        assert result == []
        service.repository.list_for_connection.assert_called_once_with(
            service.db, 12, 44, 10, 7
        )

    def test_missing_linked_identity_returns_empty_read_pages(self):
        service = _service()
        service.repository.get_identity.return_value = None

        with patch(
            "services.group_app_access_service.AppCollaborationRepository"
        ) as collaboration_repository:
            collaboration_repository.return_value.can_user_administer_app.return_value = True
            rules = service.list_rules(app_id=12, user_id=31, offset=3, limit=9)
            groups = service.list_eligible_groups(
                app_id=12, user_id=31, offset=3, limit=9
            )

        assert rules == []
        assert (groups.items, groups.total, groups.offset, groups.limit) == (
            [],
            0,
            3,
            9,
        )
        service.repository.list_for_connection.assert_not_called()
        service.repository.list_eligible_groups.assert_not_called()

    @pytest.mark.parametrize("role", ["owner", "administrator", "guest", None])
    def test_create_rejects_roles_outside_viewer_and_editor(self, role):
        service = _service()
        service.repository.get_identity.return_value = SimpleNamespace(connection_id=44)

        with patch(
            "services.group_app_access_service.AppCollaborationRepository"
        ) as collaboration_repository:
            collaboration_repository.return_value.can_user_administer_app.return_value = True
            with pytest.raises(GroupAppAccessInvalidRoleError):
                service.create_rule(
                    app_id=12,
                    user_id=31,
                    group_id=91,
                    role=role,
                )

        service.repository.get_group.assert_not_called()
        service.repository.upsert_rule.assert_not_called()

    @pytest.mark.parametrize("role", ["owner", "administrator"])
    def test_update_rejects_elevated_roles_before_loading_or_persisting_rule(self, role):
        service = _service()
        service.repository.get_identity.return_value = SimpleNamespace(connection_id=44)

        with patch(
            "services.group_app_access_service.AppCollaborationRepository"
        ) as collaboration_repository:
            collaboration_repository.return_value.can_user_administer_app.return_value = True
            with pytest.raises(GroupAppAccessInvalidRoleError):
                service.update_rule(
                    app_id=12,
                    rule_id=54,
                    user_id=31,
                    role=role,
                    is_active=None,
                )

        service.repository.get_rule_for_connection.assert_not_called()
        service.repository.update_rule.assert_not_called()

    def test_create_requires_group_from_the_callers_connection(self):
        service = _service()
        service.repository.get_identity.return_value = SimpleNamespace(connection_id=44)
        service.repository.get_group.return_value = None

        with patch(
            "services.group_app_access_service.AppCollaborationRepository"
        ) as collaboration_repository:
            collaboration_repository.return_value.can_user_administer_app.return_value = True
            with pytest.raises(GroupAppAccessNotFoundError):
                service.create_rule(
                    app_id=12,
                    user_id=31,
                    group_id=91,
                    role=GroupAppAccessRole.VIEWER,
                )

        service.repository.get_group.assert_called_once_with(
            service.db, 12, 91, 44
        )
        service.repository.upsert_rule.assert_not_called()

    def test_create_rejects_absent_linked_identity(self):
        service = _service()
        service.repository.get_identity.return_value = None

        with patch(
            "services.group_app_access_service.AppCollaborationRepository"
        ) as collaboration_repository:
            collaboration_repository.return_value.can_user_administer_app.return_value = True
            with pytest.raises(GroupAppAccessForbiddenError):
                service.create_rule(
                    app_id=12,
                    user_id=31,
                    group_id=91,
                    role=GroupAppAccessRole.EDITOR,
                )

        service.repository.get_group.assert_not_called()
        service.repository.upsert_rule.assert_not_called()


class TestGroupAppAccessRoleBoundaries:
    def test_role_validator_accepts_only_supported_group_contributions(self):
        assert GroupAppAccessService._validate_role("viewer") is GroupAppAccessRole.VIEWER
        assert GroupAppAccessService._validate_role("editor") is GroupAppAccessRole.EDITOR

        for unsupported in ("owner", "administrator", "user", "guest"):
            with pytest.raises(GroupAppAccessInvalidRoleError):
                GroupAppAccessService._validate_role(unsupported)

    def test_group_role_reads_do_not_materialize_collaborators_or_commit(self):
        db = MagicMock()
        service = _service(db)

        with patch(
            "services.group_app_access_service.AppRoleRepository"
        ) as role_repository:
            role_repository.return_value.get_effective_group_roles.return_value = {
                12: GroupAppAccessRole.EDITOR
            }
            result = service.effective_group_roles(user_id=31, app_ids=[12])

        assert result == {12: GroupAppAccessRole.EDITOR}
        role_repository.return_value.get_effective_group_roles.assert_called_once_with(
            31, [12]
        )
        db.add.assert_not_called()
        db.delete.assert_not_called()
        db.commit.assert_not_called()
