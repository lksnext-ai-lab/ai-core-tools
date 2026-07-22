"""Unit tests: resolve_user_app_role must resolve purely from ownership/
collaboration — no omniadmin bypass. Omniadmin privileges are platform-level
only (require_admin / is_omniadmin checks in routers/internal/admin.py),
not an automatic all-apps AppRole.

No DB required for the enum/hierarchy assertions; a mocked Session covers the
ownership/collaboration lookups.
Run with: pytest tests/unit/routers/test_role_authorization_no_omniadmin_bypass.py -v
"""

from unittest.mock import MagicMock

from routers.controls.role_authorization import AppRole, ROLE_HIERARCHY, resolve_user_app_role


def test_app_role_enum_has_no_omniadmin_value():
    assert not hasattr(AppRole, "OMNIADMIN")
    assert "omniadmin" not in [r.value for r in AppRole]


def test_role_hierarchy_has_no_omniadmin_entry():
    assert "omniadmin" not in [r.value for r in ROLE_HIERARCHY]


def test_resolve_user_app_role_ignores_email_parameter_and_falls_back_to_ownership():
    """A user with no ownership/collaboration on the app gets AppRole.USER,
    regardless of whether their email is a configured omniadmin — the function
    no longer accepts/uses an email argument at all."""
    db = MagicMock()
    app = MagicMock(app_id=1, owner_id=999)
    db.query.return_value.filter.return_value.first.side_effect = [app, None]

    role = resolve_user_app_role(db, app_id=1, user_id=42)

    assert role == AppRole.USER
