"""Unit tests for the domain tenant-scoping dependencies (routers/controls/domain_scope.py)."""

from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

# Load the routers package first: role_authorization -> routers.internal -> ... has an import
# cycle that only resolves in the app's normal import order.
import routers.internal  # noqa: F401
from routers.controls.domain_scope import (
    DOMAIN_NOT_FOUND,
    validate_domain_app_ownership,
    validate_domain_app_ownership_allow_new,
)


def _db(domain_app_id):
    """Session whose ``query(Domain.app_id)...scalar()`` returns ``domain_app_id``."""
    db = MagicMock()
    db.query.return_value.filter.return_value.scalar.return_value = domain_app_id
    return db


def test_domain_of_the_app_passes():
    validate_domain_app_ownership(app_id=1, domain_id=5, db=_db(1), role=None)


@pytest.mark.parametrize("domain_app_id", [2, None], ids=["other_app", "missing"])
def test_other_app_or_missing_domain_is_404(domain_app_id):
    with pytest.raises(HTTPException) as exc:
        validate_domain_app_ownership(app_id=1, domain_id=5, db=_db(domain_app_id), role=None)
    assert exc.value.status_code == 404
    assert exc.value.detail == DOMAIN_NOT_FOUND


def test_strict_variant_rejects_new_domain_id_zero():
    with pytest.raises(HTTPException) as exc:
        validate_domain_app_ownership(app_id=1, domain_id=0, db=_db(None), role=None)
    assert exc.value.status_code == 404


def test_allow_new_variant_lets_zero_through_without_querying():
    db = _db(None)
    validate_domain_app_ownership_allow_new(app_id=1, domain_id=0, db=db, role=None)
    db.query.assert_not_called()


def test_allow_new_variant_still_scopes_real_ids():
    validate_domain_app_ownership_allow_new(app_id=1, domain_id=5, db=_db(1), role=None)
    with pytest.raises(HTTPException) as exc:
        validate_domain_app_ownership_allow_new(app_id=1, domain_id=5, db=_db(2), role=None)
    assert exc.value.status_code == 404
