"""Unit tests: app roles come from app-scoped access sources, never platform role.

Omniadmin privileges are platform-level only (require_admin / is_omniadmin
checks in routers/internal/admin.py), not an automatic all-apps AppRole.
Run with: pytest tests/unit/routers/test_role_authorization_no_omniadmin_bypass.py -v
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

# Prime the internal router package after pytest has loaded conftest settings.
import routers.internal  # noqa: F401

from routers.controls.role_authorization import (
    AppRole,
    ROLE_HIERARCHY,
    require_min_role,
)
from utils.config import is_omniadmin


def test_app_role_enum_has_no_omniadmin_value():
    assert not hasattr(AppRole, "OMNIADMIN")
    assert "omniadmin" not in [r.value for r in AppRole]


def test_role_hierarchy_has_no_omniadmin_entry():
    assert "omniadmin" not in [r.value for r in ROLE_HIERARCHY]


@patch("routers.controls.role_authorization.AppRoleService")
def test_omniadmin_identity_without_app_access_is_denied_by_app_role_checker(
    app_role_service,
):
    """Platform omniadmin status does not satisfy a protected app-level role."""
    db = MagicMock()
    app_role_service.return_value.get_effective_roles.return_value = {1: "user"}
    auth_context = SimpleNamespace(
        identity=SimpleNamespace(
            id="42",
            email="admin@test.com",
        )
    )

    assert is_omniadmin(auth_context.identity.email)

    with pytest.raises(HTTPException) as exc_info:
        require_min_role(AppRole.EDITOR)(
            app_id=1,
            auth_context=auth_context,
            db=db,
        )

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "Insufficient permissions"
    app_role_service.return_value.get_effective_roles.assert_called_once_with(
        42, [1]
    )
