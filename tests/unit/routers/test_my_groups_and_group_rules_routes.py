from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException
from fastapi.routing import APIRoute

from routers.internal.auth_utils import get_current_user_oauth
from routers.internal.my_groups import router as my_groups_router
from routers.internal.scim_group_rules import (
    require_group_app_manager,
    router as group_rules_router,
)
from services.group_app_access_service import GroupAppAccessForbiddenError
from services.group_app_access_service import GroupAppAccessInvalidRoleError
from services.my_groups_service import MyGroupNotFoundError


class TestMyGroupsReadOnlyRoutes:
    def test_my_groups_routes_are_authenticated_get_only_endpoints(self):
        routes = [route for route in my_groups_router.routes if isinstance(route, APIRoute)]

        assert {route.path for route in routes} == {
            "/my-groups",
            "/my-groups/{group_id}/apps",
        }
        for route in routes:
            assert route.methods == {"GET"}
            assert any(
                dependency.call is get_current_user_oauth
                for dependency in route.dependant.dependencies
            )

    @pytest.mark.asyncio
    async def test_group_detail_maps_ineligibility_to_not_found(self, monkeypatch):
        import routers.internal.my_groups as my_groups_module

        run_in_threadpool = AsyncMock(side_effect=MyGroupNotFoundError("hidden"))
        monkeypatch.setattr(my_groups_module, "run_in_threadpool", run_in_threadpool)
        auth_context = SimpleNamespace(identity=SimpleNamespace(id="27"))

        with pytest.raises(HTTPException) as exc_info:
            await my_groups_module.list_my_group_apps(
                group_id=91,
                auth_context=auth_context,
                db=MagicMock(),
                offset=2,
                limit=3,
            )

        assert exc_info.value.status_code == 404
        assert exc_info.value.detail == "Group not found."
        assert run_in_threadpool.await_args.args[1:] == (27, 91, 2, 3)


class TestGroupRuleManagerRoutes:
    def test_every_group_rule_endpoint_requires_oauth_and_manager_dependency(self):
        routes = [
            route for route in group_rules_router.routes if isinstance(route, APIRoute)
        ]

        assert len(routes) == 5
        for route in routes:
            assert any(
                dependency.call is get_current_user_oauth
                for dependency in route.dependant.dependencies
            )
            assert any(
                dependency.call is require_group_app_manager
                for dependency in route.dependant.dependencies
            )

    @pytest.mark.asyncio
    async def test_manager_dependency_returns_forbidden_when_authorization_fails(
        self, monkeypatch
    ):
        import routers.internal.scim_group_rules as group_rules_module

        service = MagicMock()
        service.authorize_manager.side_effect = GroupAppAccessForbiddenError("denied")
        monkeypatch.setattr(group_rules_module, "_service", lambda _db: service)
        auth_context = SimpleNamespace(identity=SimpleNamespace(id="27"))

        with pytest.raises(HTTPException) as exc_info:
            group_rules_module.require_group_app_manager(
                app_id=12,
                auth_context=auth_context,
                db=MagicMock(),
            )

        assert exc_info.value.status_code == 403
        service.authorize_manager.assert_called_once_with(12, 27)

    @pytest.mark.asyncio
    async def test_patch_maps_elevated_policy_role_rejection_to_422(self, monkeypatch):
        import routers.internal.scim_group_rules as group_rules_module

        run_in_threadpool = AsyncMock(
            side_effect=GroupAppAccessInvalidRoleError("unsupported")
        )
        monkeypatch.setattr(group_rules_module, "run_in_threadpool", run_in_threadpool)
        auth_context = SimpleNamespace(identity=SimpleNamespace(id="27"))

        with pytest.raises(HTTPException) as exc_info:
            await group_rules_module.update_group_rule(
                app_id=12,
                rule_id=54,
                payload=SimpleNamespace(role="owner", is_active=None),
                auth_context=auth_context,
                db=MagicMock(),
            )

        assert exc_info.value.status_code == 422
        assert exc_info.value.detail == "Only VIEWER and EDITOR group roles are supported."
