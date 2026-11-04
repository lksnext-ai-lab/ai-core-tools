from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from models.embedding_service import EmbeddingService
from services import service_health_service
from services.service_health_service import ServiceHealthService
from utils.provider_errors import ProviderError, ProviderErrorKind

AUTH = ProviderError(ProviderErrorKind.AUTH, "Embedding service 'small' rejected its credentials.")
OTHER = ProviderError(ProviderErrorKind.OTHER, "Indexing failed (RuntimeError).")


@pytest.fixture
def session():
    s = MagicMock()
    with patch.object(service_health_service, "SessionLocal", return_value=s):
        yield s


def _update_values(session):
    return session.query.return_value.filter.return_value.update.call_args.args[0]


class TestRecordFailure:
    def test_auth_error_is_stored_on_the_service(self, session):
        ServiceHealthService.record_failure(EmbeddingService, SimpleNamespace(service_id=10), AUTH)

        values = _update_values(session)
        assert values[EmbeddingService.last_error] == AUTH.message
        assert values[EmbeddingService.last_error_at] is not None
        session.commit.assert_called_once()
        session.close.assert_called_once()

    @pytest.mark.parametrize("service, error", [
        (SimpleNamespace(service_id=10), OTHER),  # not fixable on the service
        (None, AUTH),                             # no service to blame
    ])
    def test_nothing_is_written(self, session, service, error):
        ServiceHealthService.record_failure(EmbeddingService, service, error)
        session.query.assert_not_called()

    def test_db_failure_is_swallowed(self, session):
        session.commit.side_effect = RuntimeError("db down")

        ServiceHealthService.record_failure(EmbeddingService, SimpleNamespace(service_id=10), AUTH)

        session.rollback.assert_called_once()
        session.close.assert_called_once()


class TestRecordSuccess:
    def test_recorded_error_is_cleared(self, session):
        ServiceHealthService.record_success(EmbeddingService, SimpleNamespace(service_id=10, last_error="x"))

        values = _update_values(session)
        assert values == {EmbeddingService.last_error: None, EmbeddingService.last_error_at: None}
        session.commit.assert_called_once()

    @pytest.mark.parametrize("service", [None, SimpleNamespace(service_id=10, last_error=None)])
    def test_healthy_service_costs_no_query(self, session, service):
        ServiceHealthService.record_success(EmbeddingService, service)
        session.query.assert_not_called()

    def test_db_failure_is_swallowed(self, session):
        session.commit.side_effect = RuntimeError("db down")

        ServiceHealthService.record_success(EmbeddingService, SimpleNamespace(service_id=10, last_error="x"))

        session.rollback.assert_called_once()
        session.close.assert_called_once()
