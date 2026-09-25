"""SkillRepository.delete must never leave the session in a failed state or leak untyped errors."""
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.exc import IntegrityError, OperationalError

from repositories.skill_repository import SkillRepository


@pytest.mark.parametrize("exc", [
    IntegrityError("stmt", {}, Exception("fk")),
    OperationalError("stmt", {}, Exception("conn")),
    AssertionError("rowcount"),
])
def test_commit_failure_rolls_back_and_raises_plain_runtime_error(exc):
    """The repository never makes an HTTP-status decision: it raises a plain RuntimeError, not a
    services.skill_errors type (that translation is SkillService's job)."""
    db = MagicMock()
    db.commit.side_effect = exc
    with patch("repositories.skill_repository.SkillPackageRepository"):
        with pytest.raises(RuntimeError) as ei:
            SkillRepository.delete(db, SimpleNamespace(skill_id=5))
    db.rollback.assert_called_once()
    assert "retry" in str(ei.value)
    assert type(ei.value) is RuntimeError


def test_success_deletes_associations_files_and_commits():
    db = MagicMock()
    with patch("repositories.skill_repository.SkillPackageRepository") as pkg:
        SkillRepository.delete(db, SimpleNamespace(skill_id=5))
    pkg.delete_all_for_skill.assert_called_once_with(db, 5)
    db.commit.assert_called_once()
    db.rollback.assert_not_called()
