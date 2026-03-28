"""Integration tests for EmbeddingServiceRepository.get_system_services.

Requires test DB on port 5433.
Run with: pytest tests/integration/test_embedding_service_repository.py -v
"""
import pytest
from datetime import datetime


class TestGetSystemServices:

    def test_get_system_services_returns_only_null_app_id(self, db, fake_app):
        """get_system_services returns only services with app_id IS NULL."""
        from models.embedding_service import EmbeddingService
        from repositories.embedding_service_repository import EmbeddingServiceRepository

        # App-scoped service
        app_svc = EmbeddingService(
            name="App Embeddings",
            provider="OpenAI",
            api_key="sk-app",  # pragma: allowlist secret
            description="text-embedding-ada-002",
            endpoint="",
            app_id=fake_app.app_id,
            create_date=datetime.now(),
        )
        db.add(app_svc)

        # System service (app_id=None)
        sys_svc = EmbeddingService(
            name="System Embeddings",
            provider="OpenAI",
            api_key="sk-sys",  # pragma: allowlist secret
            description="text-embedding-3-small",
            endpoint="",
            app_id=None,
            create_date=datetime.now(),
        )
        db.add(sys_svc)
        db.flush()

        result = EmbeddingServiceRepository.get_system_services(db)

        assert len(result) == 1
        assert result[0].service_id == sys_svc.service_id

    def test_get_by_app_id_excludes_system_services(self, db, fake_app):
        """get_by_app_id returns only app-scoped services, not system ones."""
        from models.embedding_service import EmbeddingService
        from repositories.embedding_service_repository import EmbeddingServiceRepository

        # App-scoped service
        app_svc = EmbeddingService(
            name="App Embeddings",
            provider="OpenAI",
            api_key="sk-app",  # pragma: allowlist secret
            description="text-embedding-ada-002",
            endpoint="",
            app_id=fake_app.app_id,
            create_date=datetime.now(),
        )
        db.add(app_svc)

        # System service (app_id=None)
        sys_svc = EmbeddingService(
            name="System Embeddings",
            provider="OpenAI",
            api_key="sk-sys",  # pragma: allowlist secret
            description="text-embedding-3-small",
            endpoint="",
            app_id=None,
            create_date=datetime.now(),
        )
        db.add(sys_svc)
        db.flush()

        result = EmbeddingServiceRepository.get_by_app_id(db, fake_app.app_id)

        assert len(result) == 1
        assert result[0].service_id == app_svc.service_id
        service_ids = [s.service_id for s in result]
        assert sys_svc.service_id not in service_ids
