"""
Unit tests for the vector_db_type immutability guard in RepositoryService.

Mirrors the pattern established for silos (test_silo_service_vector_db_immutability.py).

The guard lives in two places:
  1. utils/vector_db_immutability.py  — shared helper (unit-tested directly here)
  2. RepositoryService.update_repository() — integration point (tested via the service)

No database is needed — ORM objects and sessions are fully mocked.
"""

import pytest
from unittest.mock import MagicMock, patch

from utils.vector_db_immutability import assert_vector_db_type_immutable
from utils.error_handlers import ValidationError


# ---------------------------------------------------------------------------
# Direct tests for the shared guard utility
# ---------------------------------------------------------------------------

class TestAssertVectorDbTypeImmutable:
    """Unit tests for utils/vector_db_immutability.assert_vector_db_type_immutable."""

    # Rejection cases

    def test_raises_when_changing_pgvector_to_qdrant(self):
        with pytest.raises(ValidationError) as exc:
            assert_vector_db_type_immutable("PGVECTOR", "QDRANT", "repository")
        assert "vector_db_type cannot be changed" in str(exc.value)
        assert "repository" in str(exc.value)

    def test_raises_when_changing_qdrant_to_pgvector(self):
        with pytest.raises(ValidationError):
            assert_vector_db_type_immutable("QDRANT", "PGVECTOR", "repository")

    def test_raises_regardless_of_input_case(self):
        """Comparison is case-insensitive — lowercase requested value is still rejected."""
        with pytest.raises(ValidationError):
            assert_vector_db_type_immutable("PGVECTOR", "qdrant", "repository")

    def test_raises_regardless_of_stored_case(self):
        """Stored value normalised as well."""
        with pytest.raises(ValidationError):
            assert_vector_db_type_immutable("pgvector", "QDRANT", "repository")

    # Accepted cases

    def test_same_value_is_accepted(self):
        assert_vector_db_type_immutable("PGVECTOR", "PGVECTOR", "repository")  # no raise

    def test_same_value_different_case_is_accepted(self):
        assert_vector_db_type_immutable("PGVECTOR", "pgvector", "repository")  # no raise

    def test_none_requested_is_accepted(self):
        """Caller omitted the field — nothing to enforce."""
        assert_vector_db_type_immutable("PGVECTOR", None, "repository")  # no raise

    def test_none_existing_is_accepted(self):
        """Legacy row with no stored value — guard stays silent."""
        assert_vector_db_type_immutable(None, "QDRANT", "repository")  # no raise

    def test_both_none_is_accepted(self):
        assert_vector_db_type_immutable(None, None, "repository")  # no raise

    def test_default_entity_name_used_in_message(self):
        """Default entity name is 'resource' when not specified."""
        with pytest.raises(ValidationError) as exc:
            assert_vector_db_type_immutable("PGVECTOR", "QDRANT")
        assert "resource" in str(exc.value)


# ---------------------------------------------------------------------------
# RepositoryService.update_repository() — guard integration
# ---------------------------------------------------------------------------

def _make_silo_mock(vector_db_type: str | None = "PGVECTOR") -> MagicMock:
    silo = MagicMock()
    silo.vector_db_type = vector_db_type
    silo.embedding_service_id = None
    return silo


def _make_repository_mock(vector_db_type: str | None = "PGVECTOR") -> MagicMock:
    repo = MagicMock()
    repo.repository_id = 1
    repo.app_id = 10
    repo.silo = _make_silo_mock(vector_db_type)
    return repo


class TestRepositoryServiceUpdateGuard:
    """Guard is enforced inside RepositoryService.update_repository()."""

    def _call_update(self, repository: MagicMock, vector_db_type: str | None):
        from services.repository_service import RepositoryService
        from repositories.repository_repository import RepositoryRepository

        mock_db = MagicMock()

        with patch.object(RepositoryRepository, "update", return_value=repository):
            return RepositoryService.update_repository(
                repository,
                embedding_service_id=None,
                vector_db_type=vector_db_type,
                db=mock_db,
            )

    # Rejection cases

    def test_raises_when_changing_pgvector_to_qdrant(self):
        repo = _make_repository_mock(vector_db_type="PGVECTOR")
        with pytest.raises(ValidationError) as exc:
            self._call_update(repo, "QDRANT")
        assert "vector_db_type cannot be changed" in str(exc.value)

    def test_raises_when_changing_qdrant_to_pgvector(self):
        repo = _make_repository_mock(vector_db_type="QDRANT")
        with pytest.raises(ValidationError):
            self._call_update(repo, "PGVECTOR")

    def test_raises_regardless_of_input_case(self):
        repo = _make_repository_mock(vector_db_type="PGVECTOR")
        with pytest.raises(ValidationError):
            self._call_update(repo, "qdrant")

    # Accepted cases

    def test_same_value_is_accepted(self):
        repo = _make_repository_mock(vector_db_type="PGVECTOR")
        result = self._call_update(repo, "PGVECTOR")
        assert result is not None

    def test_omitted_vector_db_type_is_accepted(self):
        """None means the caller did not supply the field — must pass through."""
        repo = _make_repository_mock(vector_db_type="PGVECTOR")
        result = self._call_update(repo, None)
        assert result is not None

    def test_null_stored_value_skips_guard(self):
        """Legacy repository with no stored vector_db_type — guard must not fire."""
        repo = _make_repository_mock(vector_db_type=None)
        result = self._call_update(repo, "QDRANT")
        assert result is not None

    def test_no_silo_skips_guard(self):
        """Repository without a silo — nothing to protect."""
        repo = _make_repository_mock()
        repo.silo = None  # detach silo

        from services.repository_service import RepositoryService
        from repositories.repository_repository import RepositoryRepository

        mock_db = MagicMock()
        with patch.object(RepositoryRepository, "update", return_value=repo):
            result = RepositoryService.update_repository(repo, vector_db_type="QDRANT", db=mock_db)
        assert result is not None
