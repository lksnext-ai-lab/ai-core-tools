from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from models.app_collaborator import CollaborationRole
from models.group_app_access_rule import GroupAppAccessRole
from repositories.app_role_repository import AppRoleSource
from services.app_role_service import AppRoleService


def _source(app_id, owner_id, collaboration_role=None, group_role=None):
    return AppRoleSource(
        app=SimpleNamespace(app_id=app_id, owner_id=owner_id),
        collaboration_role=collaboration_role,
        group_role=group_role,
    )


class TestEffectiveAppRoleResolution:
    def test_group_role_does_not_demote_manual_administrator(self):
        source = _source(
            1,
            99,
            collaboration_role=CollaborationRole.ADMINISTRATOR,
            group_role=GroupAppAccessRole.EDITOR,
        )

        assert AppRoleService._combine_role_sources(42, [source]) == {
            1: "administrator"
        }

    def test_group_only_app_role_is_resolved_for_the_full_app_scope(self):
        with patch("services.app_role_service.AppRoleRepository") as repository:
            repository.return_value.get_app_role_sources.return_value = [
                _source(1, 99, group_role=GroupAppAccessRole.EDITOR)
            ]
            roles = AppRoleService(MagicMock()).get_effective_roles(42, [1])

        assert roles == {1: "editor"}
        repository.return_value.get_app_role_sources.assert_called_once_with(
            42, [1]
        )

    def test_owner_collaboration_and_group_access_use_app_role_precedence(self):
        db = MagicMock()
        sources = [
            _source(1, 7, group_role=GroupAppAccessRole.EDITOR),
            _source(
                2,
                99,
                collaboration_role=CollaborationRole.ADMINISTRATOR,
                group_role=GroupAppAccessRole.EDITOR,
            ),
            _source(
                3,
                99,
                collaboration_role=CollaborationRole.VIEWER,
                group_role=GroupAppAccessRole.EDITOR,
            ),
            _source(4, 99, group_role=GroupAppAccessRole.VIEWER),
            # Platform roles are not a source in AppRoleSource and cannot grant
            # app access independently of ownership/collaboration/group policy.
            _source(5, 99, group_role="administrator"),
        ]

        with patch("services.app_role_service.AppRoleRepository") as repository:
            repository.return_value.get_app_role_sources.return_value = sources
            result = AppRoleService(db).get_effective_roles(
                user_id=7, app_ids=[1, 2, 3, 4, 5]
            )

        assert result == {
            1: "owner",
            2: "administrator",
            3: "editor",
            4: "viewer",
            5: "user",
        }
        repository.return_value.get_app_role_sources.assert_called_once_with(
            7, [1, 2, 3, 4, 5]
        )
        db.add.assert_not_called()
        db.delete.assert_not_called()
        db.commit.assert_not_called()

    def test_invalid_and_duplicate_app_ids_are_filtered_before_source_lookup(self):
        with patch("services.app_role_service.AppRoleRepository") as repository:
            repository.return_value.get_app_role_sources.return_value = []
            result = AppRoleService(MagicMock()).get_effective_roles(
                user_id=7, app_ids=[3, -1, 3, 0, 9]
            )

        assert result == {}
        repository.return_value.get_app_role_sources.assert_called_once_with(
            7, [3, 9]
        )

    def test_invalid_user_or_empty_scope_skips_repository(self):
        with patch("services.app_role_service.AppRoleRepository") as repository:
            service = AppRoleService(MagicMock())

            assert service.get_effective_roles(user_id=0, app_ids=[3]) == {}
            assert service.get_effective_roles(user_id=7, app_ids=[]) == {}

        repository.return_value.get_app_role_sources.assert_not_called()

    def test_accessible_app_page_preserves_pagination_and_filters_inaccessible_roles(self):
        sources = [
            _source(1, 7),
            _source(2, 99, collaboration_role=CollaborationRole.USER),
            _source(3, 99, group_role=GroupAppAccessRole.VIEWER),
        ]
        with patch("services.app_role_service.AppRoleRepository") as repository:
            repository.return_value.get_accessible_app_role_sources.return_value = (
                sources,
                True,
            )
            apps, roles, has_more = AppRoleService(MagicMock()).get_accessible_apps_with_roles(
                user_id=7, limit=2, offset=4
            )

        assert [app.app_id for app in apps] == [1, 3]
        assert roles == {1: "owner", 3: "viewer"}
        assert has_more is True
        repository.return_value.get_accessible_app_role_sources.assert_called_once_with(
            7, 2, 4
        )
