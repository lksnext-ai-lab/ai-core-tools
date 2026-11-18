from unittest.mock import MagicMock, patch

import pytest

from services.my_groups_service import MyGroupNotFoundError, MyGroupsService


def _service_with_mock_repository():
    db = MagicMock()
    with patch("services.my_groups_service.MyGroupsRepository") as repository_class:
        service = MyGroupsService(db)
    return service, repository_class.return_value


def test_list_group_apps_resolves_effective_roles_for_page_in_one_batch():
    db = MagicMock()
    service = MyGroupsService(db)
    service.repository.list_group_apps = MagicMock(
        return_value=(
            "Engineering",
            [
                (11, "App One", "viewer"),
                (22, "App Two", "editor"),
            ],
            2,
        )
    )

    with patch(
        "services.my_groups_service.AppRoleService"
    ) as app_role_service_class:
        app_role_service_class.return_value.get_effective_roles.return_value = {
            11: "editor",
            22: "owner",
        }

        result = service.list_group_apps(user_id=7, group_id=3, offset=0, limit=50)

    app_role_service_class.assert_called_once_with(db)
    app_role_service_class.return_value.get_effective_roles.assert_called_once_with(
        7, [11, 22]
    )
    assert [item.effective_role for item in result.items] == ["editor", "owner"]
    assert [item.contribution.value for item in result.items] == ["VIEWER", "EDITOR"]
    assert result.total == 2


class TestMyGroupsService:
    def test_group_list_is_scoped_and_preserves_pagination_metadata(self):
        service, repository = _service_with_mock_repository()
        repository.list_groups.return_value = (
            [(8, "Engineering"), (13, "Support")],
            6,
        )

        result = service.list_groups(user_id=27, offset=4, limit=2)

        repository.list_groups.assert_called_once_with(service.db, 27, 4, 2)
        assert [(item.group_id, item.display_name) for item in result.items] == [
            (8, "Engineering"),
            (13, "Support"),
        ]
        assert (result.total, result.offset, result.limit) == (6, 4, 2)

    def test_group_apps_are_scoped_to_user_and_group_and_preserve_pagination(self):
        service, repository = _service_with_mock_repository()
        repository.list_group_apps.return_value = (
            "Engineering",
            [(22, "Internal Tools", "editor")],
            5,
        )

        with patch("services.my_groups_service.AppRoleService") as role_service:
            role_service.return_value.get_effective_roles.return_value = {
                22: "administrator"
            }
            result = service.list_group_apps(
                user_id=27, group_id=8, offset=3, limit=1
            )

        repository.list_group_apps.assert_called_once_with(service.db, 27, 8, 3, 1)
        assert (result.group_id, result.display_name) == (8, "Engineering")
        assert (result.total, result.offset, result.limit) == (5, 3, 1)
        assert result.items[0].contribution.value == "EDITOR"
        assert result.items[0].effective_role == "administrator"

    def test_group_apps_hide_groups_without_current_eligibility(self):
        service, repository = _service_with_mock_repository()
        repository.list_group_apps.return_value = None

        with pytest.raises(MyGroupNotFoundError, match="Group not found"):
            service.list_group_apps(user_id=27, group_id=8, offset=0, limit=50)

        repository.list_group_apps.assert_called_once_with(service.db, 27, 8, 0, 50)

    def test_empty_group_app_page_resolves_with_no_app_ids(self):
        service, repository = _service_with_mock_repository()
        repository.list_group_apps.return_value = ("Engineering", [], 0)

        with patch("services.my_groups_service.AppRoleService") as role_service:
            result = service.list_group_apps(
                user_id=27, group_id=8, offset=5, limit=50
            )

        repository.list_group_apps.assert_called_once_with(service.db, 27, 8, 5, 50)
        assert (result.group_id, result.display_name) == (8, "Engineering")
        assert result.items == []
        assert (result.total, result.offset, result.limit) == (0, 5, 50)
        role_service.return_value.get_effective_roles.assert_called_once_with(
            27, []
        )
