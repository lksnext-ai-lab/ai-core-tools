"""Unit tests: retired services cannot be newly assigned (FR-11, D-4, AC-17).

Covers agents (incl. OCR vision / media embedding), silos, repositories and middlewares.
No database: repositories and sessions are mocked.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from services.agent_service import AgentService
from services.middleware_service import MiddlewareService, MiddlewareValidationError
from services.repository_service import RepositoryService
from services.silo_service import SiloService
from models.middleware import MiddlewareType
from utils.error_handlers import ValidationError
from utils.service_lifecycle import RetiredServiceAssignmentError

PAST = datetime.now(timezone.utc) - timedelta(days=3)
FUTURE = datetime.now(timezone.utc) + timedelta(days=30)


def _svc(service_id: int, retired: bool = False, supports_video: bool = True, app_id=10) -> MagicMock:
    s = MagicMock()
    s.service_id = service_id
    s.name = f"svc{service_id}"
    s.app_id = app_id
    s.supports_video = supports_video
    s.end_of_service_at = PAST if retired else None
    return s


# ---------------------------------------------------------------------------
# Agents
# ---------------------------------------------------------------------------

AI_REPO = "repositories.ai_service_repository.AIServiceRepository.get_by_id"
EMB_REPO = "repositories.embedding_service_repository.EmbeddingServiceRepository.get_by_id"


def _agent(**fields) -> MagicMock:
    agent = MagicMock()
    for key in ("service_id", "vision_service_id", "transcription_service_id",
                "video_ai_service_id", "media_embedding_service_id"):
        setattr(agent, key, fields.get(key))
    return agent


class TestAgentAssignment:
    def _validate(self, data: dict, existing=None):
        AgentService()._validate_referenced_resource_ids(MagicMock(), {"app_id": 10, **data}, existing)

    def test_update_changing_service_to_retired_rejected(self):
        with patch(AI_REPO, return_value=_svc(2, retired=True)):
            with pytest.raises(ValueError, match="service_id"):
                self._validate({"service_id": 2}, _agent(service_id=1))

    def test_retired_error_is_value_error_subclass(self):
        with patch(AI_REPO, return_value=_svc(2, retired=True)):
            with pytest.raises(RetiredServiceAssignmentError):
                self._validate({"service_id": 2}, _agent(service_id=1))

    def test_unchanged_retired_reference_accepted(self):
        with patch(AI_REPO, return_value=_svc(2, retired=True)):
            self._validate({"service_id": 2, "name": "renamed"}, _agent(service_id=2))

    def test_field_absent_from_payload_is_not_checked(self):
        with patch(AI_REPO, side_effect=AssertionError("must not load")):
            self._validate({"name": "x"}, _agent(service_id=2))

    def test_new_agent_with_retired_service_rejected(self):
        with patch(AI_REPO, return_value=_svc(2, retired=True)):
            with pytest.raises(ValueError):
                self._validate({"service_id": 2}, None)

    def test_deprecated_or_active_service_accepted(self):
        active = _svc(3)
        active.end_of_service_at = FUTURE
        with patch(AI_REPO, return_value=active):
            self._validate({"service_id": 3}, None)

    @pytest.mark.parametrize("field", ["vision_service_id", "transcription_service_id", "video_ai_service_id"])
    def test_ai_backed_fields_rejected_when_changed(self, field):
        with patch(AI_REPO, return_value=_svc(2, retired=True)):
            with pytest.raises(ValueError, match=field):
                self._validate({field: 2}, _agent(**{field: 1}))

    @pytest.mark.parametrize("field", ["vision_service_id", "transcription_service_id", "video_ai_service_id"])
    def test_ai_backed_fields_accepted_when_unchanged(self, field):
        with patch(AI_REPO, return_value=_svc(2, retired=True)):
            self._validate({field: 2}, _agent(**{field: 2}))

    def test_ocr_vision_new_retired_rejected(self):
        with patch(AI_REPO, return_value=_svc(2, retired=True)):
            with pytest.raises(ValueError, match="vision_service_id"):
                self._validate({"vision_service_id": 2}, None)

    def test_media_embedding_retired_rejected(self):
        with patch(EMB_REPO, return_value=_svc(4, retired=True)):
            with pytest.raises(ValueError, match="media_embedding_service_id"):
                self._validate({"media_embedding_service_id": 4}, _agent(media_embedding_service_id=None))

    def test_media_embedding_unchanged_accepted(self):
        with patch(EMB_REPO, return_value=_svc(4, retired=True)):
            self._validate({"media_embedding_service_id": 4}, _agent(media_embedding_service_id=4))


# ---------------------------------------------------------------------------
# Silos
# ---------------------------------------------------------------------------

def _db() -> MagicMock:
    db = MagicMock()
    db.__bool__ = lambda self: True
    return db


def _silo(embedding=None, transcription=None, video=None) -> MagicMock:
    silo = MagicMock()
    silo.silo_id = 1
    silo.app_id = 10
    silo.vector_db_type = "PGVECTOR"
    silo.silo_type = "CUSTOM"
    silo.embedding_service_id = embedding
    silo.transcription_service_id = transcription
    silo.video_ai_service_id = video
    return silo


def _silo_data(**extra) -> dict:
    return {"silo_id": 1, "app_id": 10, "name": "s", "description": "", "vector_db_type": None, **extra}


class TestSiloAssignment:
    def test_embedding_assignment_to_retired_rejected(self):
        silo = _silo()
        with patch("services.silo_service.SiloService.get_silo", return_value=silo), patch(
            "services.silo_service.SiloRepository.get_embedding_service_by_id", return_value=_svc(7, retired=True)
        ):
            with pytest.raises(ValidationError, match="retired"):
                SiloService.create_or_update_silo(_silo_data(embedding_service_id=7), db=_db())
        assert silo.embedding_service_id is None

    def test_silo_creation_with_retired_embedding_rejected(self):
        with patch("services.tier_enforcement_service.TierEnforcementService.check_resource_limit"), patch(
            "services.silo_service.SiloRepository.get_embedding_service_by_id", return_value=_svc(7, retired=True)
        ):
            with pytest.raises(ValidationError, match="retired"):
                SiloService.create_or_update_silo(_silo_data(silo_id=0, embedding_service_id=7), db=_db())

    def test_embedding_assignment_to_active_accepted(self):
        silo = _silo()
        with patch("services.silo_service.SiloService.get_silo", return_value=silo), patch(
            "services.silo_service.SiloRepository.get_embedding_service_by_id", return_value=_svc(7)
        ):
            SiloService.create_or_update_silo(_silo_data(embedding_service_id=7), db=_db())
        assert silo.embedding_service_id == 7

    @staticmethod
    def _media_db(service):
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = service
        return db

    def test_media_service_change_to_retired_rejected(self):
        silo = _silo(transcription=1)
        with pytest.raises(ValidationError, match="retired"):
            SiloService.apply_media_services(silo, 2, None, 10, self._media_db(_svc(2, retired=True)))
        assert silo.transcription_service_id == 1

    def test_video_service_change_to_retired_rejected(self):
        silo = _silo()
        with pytest.raises(ValidationError, match="retired"):
            SiloService.apply_media_services(silo, None, 2, 10, self._media_db(_svc(2, retired=True)))

    def test_media_service_unchanged_retired_accepted(self):
        silo = _silo(transcription=2, video=2)
        SiloService.apply_media_services(silo, 2, 2, 10, self._media_db(_svc(2, retired=True)))
        assert silo.transcription_service_id == 2
        assert silo.video_ai_service_id == 2


# ---------------------------------------------------------------------------
# Repositories (direct embedding assignment in update_repository)
# ---------------------------------------------------------------------------

class TestRepositoryAssignment:
    def _repo(self, embedding=None):
        repo = MagicMock()
        repo.app_id = 10
        repo.silo = _silo(embedding=embedding)
        repo.silo.vector_db_type = "PGVECTOR"
        return repo

    def test_update_assigning_retired_embedding_rejected(self):
        repo = self._repo()
        with patch("services.repository_service.EmbeddingServiceRepository.get_by_id", return_value=_svc(5, True)):
            with pytest.raises(ValidationError, match="retired"):
                RepositoryService.update_repository(repo, 5, None, MagicMock())
        assert repo.silo.embedding_service_id is None

    def test_update_unchanged_retired_embedding_accepted(self):
        repo = self._repo(embedding=5)
        with patch("services.repository_service.EmbeddingServiceRepository.get_by_id", return_value=_svc(5, True)), \
                patch("services.repository_service.RepositoryRepository.update", create=True):
            RepositoryService.update_repository(repo, 5, None, MagicMock())
        assert repo.silo.embedding_service_id == 5


# ---------------------------------------------------------------------------
# Middlewares
# ---------------------------------------------------------------------------

def _mw_data(service_id: int) -> MagicMock:
    data = MagicMock()
    data.name = "mw"
    data.description = ""
    data.middleware_type = MiddlewareType.SUMMARIZATION
    data.config = {"summarization_model": f"ai_service:{service_id}"}
    return data


class TestMiddlewareAssignment:
    MW_REPO = "services.middleware_service.MiddlewareRepository"

    def _existing(self, service_id):
        mw = MagicMock()
        mw.middleware_type = MiddlewareType.SUMMARIZATION
        mw.config = {"summarization_model": f"ai_service:{service_id}"}
        mw.agent_associations = []
        return mw

    def _run(self, middleware_id, new_id, old_id=None, retired=True):
        with patch(self.MW_REPO) as repo, patch(AI_REPO, return_value=_svc(new_id, retired=retired)), patch(
            "services.middleware_service._to_detail", return_value="ok"
        ):
            repo.name_exists.return_value = False
            repo.get_existing_ai_service_ids_for_app.return_value = {new_id}
            repo.get_by_id_and_app_id.return_value = self._existing(old_id) if old_id else None
            return MiddlewareService.create_or_update_middleware(MagicMock(), 10, middleware_id, _mw_data(new_id))

    def test_new_middleware_with_retired_service_rejected(self):
        with pytest.raises(MiddlewareValidationError, match="retired"):
            self._run(0, 5)

    def test_update_to_new_retired_service_rejected(self):
        with pytest.raises(MiddlewareValidationError, match="retired"):
            self._run(3, 5, old_id=4)

    def test_update_keeping_retired_service_accepted(self):
        assert self._run(3, 5, old_id=5) == "ok"

    def test_active_service_accepted(self):
        assert self._run(0, 5, retired=False) == "ok"


# ---------------------------------------------------------------------------
# Review fixes: playground temp repo, SharePoint 422, unparsable stored middleware config
# ---------------------------------------------------------------------------

class TestPlaygroundTempRepoRetired:
    def test_new_temp_repo_with_retired_agent_embedding_raises_service_retired(self):
        from services.playground_media_service import PlaygroundMediaService
        from utils.service_lifecycle import ServiceRetiredError

        agent = MagicMock()
        agent.media_embedding_service_id = 4
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = agent
        with patch.object(PlaygroundMediaService, "get_temp_repository", return_value=None), patch(
            EMB_REPO, return_value=_svc(4, retired=True)
        ), patch("services.playground_media_service.RepositoryService.create_repository") as create:
            with pytest.raises(ServiceRetiredError):
                PlaygroundMediaService.get_or_create_temp_repository(10, 1, "s", db)
        create.assert_not_called()

    def test_reuse_path_retired_transcription_raises_service_retired(self):
        from services.playground_media_service import PlaygroundMediaService
        from utils.service_lifecycle import ServiceRetiredError

        existing = MagicMock()
        existing.silo.transcription_service_id = 1
        existing.silo.video_ai_service_id = None
        with patch.object(PlaygroundMediaService, "get_temp_repository", return_value=existing), patch(
            AI_REPO, return_value=_svc(2, retired=True)
        ):
            with pytest.raises(ServiceRetiredError):
                PlaygroundMediaService.get_or_create_temp_repository(
                    10, 1, "s", MagicMock(), transcription_service_id=2
                )
        assert existing.silo.transcription_service_id == 1

    def test_playground_endpoints_reraise_service_retired(self):
        import inspect
        from routers.internal import agents as agents_router

        for name in ("upload_playground_media", "add_playground_youtube"):
            fn = getattr(agents_router, name, None)
            if fn is not None:
                assert "except (HTTPException, ServiceRetiredError)" in inspect.getsource(fn)


class TestSharePointCreateValidation:
    @pytest.mark.asyncio
    async def test_validation_error_maps_to_422(self):
        from fastapi import HTTPException
        from routers.internal import sharepoint as sp_router

        with patch.object(
            sp_router.SharePointSourceService, "create_source", side_effect=ValidationError("retired")
        ):
            with pytest.raises(HTTPException) as exc:
                await sp_router.create_sharepoint_source(
                    10, MagicMock(), MagicMock(), MagicMock(), MagicMock()
                )
        assert exc.value.status_code == 422
        assert "retired" in exc.value.detail


class TestMiddlewareUnparsableStoredConfig:
    def test_unchanged_retired_ref_accepted_when_stored_config_unparsable(self):
        mw = MagicMock()
        mw.middleware_type = MiddlewareType.SUMMARIZATION
        mw.config = {"summarization_model": "ai_service:5", "legacy_unknown_key": 1}
        mw.agent_associations = []
        with patch("services.middleware_service.MiddlewareRepository") as repo, patch(
            AI_REPO, return_value=_svc(5, retired=True)
        ), patch("services.middleware_service._to_detail", return_value="ok"):
            repo.name_exists.return_value = False
            repo.get_existing_ai_service_ids_for_app.return_value = {5}
            repo.get_by_id_and_app_id.return_value = mw
            assert MiddlewareService.create_or_update_middleware(MagicMock(), 10, 3, _mw_data(5)) == "ok"


# ---------------------------------------------------------------------------
# Cross-tenant embedding service ownership
# ---------------------------------------------------------------------------

GENERIC = "embedding_service_id does not exist or does not belong to this app"


class TestEmbeddingOwnership:
    @pytest.mark.parametrize("retired", [False, True])
    def test_silo_foreign_embedding_rejected_without_leaking_name(self, retired):
        silo = _silo()
        foreign = _svc(7, retired=retired, app_id=99)
        foreign.name = "SECRET-NAME"
        with patch("services.silo_service.SiloService.get_silo", return_value=silo), patch(
            "services.silo_service.SiloRepository.get_embedding_service_by_id", return_value=foreign
        ):
            with pytest.raises(ValidationError) as exc:
                SiloService.create_or_update_silo(_silo_data(embedding_service_id=7), db=_db())
        assert str(exc.value) == GENERIC or GENERIC in str(exc.value)
        assert "SECRET-NAME" not in str(exc.value)
        assert silo.embedding_service_id is None

    def test_silo_nonexistent_embedding_same_message(self):
        with patch("services.silo_service.SiloService.get_silo", return_value=_silo()), patch(
            "services.silo_service.SiloRepository.get_embedding_service_by_id", return_value=None
        ):
            with pytest.raises(ValidationError) as exc:
                SiloService.create_or_update_silo(_silo_data(embedding_service_id=7), db=_db())
        assert GENERIC in str(exc.value)

    @pytest.mark.parametrize("app_id", [10, None])
    def test_silo_own_or_system_embedding_ok(self, app_id):
        silo = _silo()
        with patch("services.silo_service.SiloService.get_silo", return_value=silo), patch(
            "services.silo_service.SiloRepository.get_embedding_service_by_id",
            return_value=_svc(7, app_id=app_id),
        ):
            SiloService.create_or_update_silo(_silo_data(embedding_service_id=7), db=_db())
        assert silo.embedding_service_id == 7

    @pytest.mark.parametrize("svc", [None, "foreign"])
    def test_repository_update_foreign_or_missing_rejected(self, svc):
        repo = MagicMock()
        repo.app_id = 10
        repo.silo = _silo()
        found = None if svc is None else _svc(5, retired=True, app_id=99)
        with patch("services.repository_service.EmbeddingServiceRepository.get_by_id", return_value=found):
            with pytest.raises(ValidationError) as exc:
                RepositoryService.update_repository(repo, 5, None, MagicMock())
        assert GENERIC in str(exc.value)
        assert repo.silo.embedding_service_id is None

    def test_repository_update_system_embedding_ok(self):
        repo = MagicMock()
        repo.app_id = 10
        repo.silo = _silo()
        with patch("services.repository_service.EmbeddingServiceRepository.get_by_id", return_value=_svc(5, app_id=None)):
            RepositoryService.update_repository(repo, 5, None, MagicMock())
        assert repo.silo.embedding_service_id == 5


# ---------------------------------------------------------------------------
# Playground temp repo ownership, silo creation ownership, repository delete ownership
# ---------------------------------------------------------------------------

class TestPlaygroundExistingRepoOwnership:
    def _existing(self):
        existing = MagicMock()
        existing.silo = _silo(transcription=1)
        return existing

    def test_foreign_transcription_service_rejected_silo_unchanged(self):
        from services.playground_media_service import PlaygroundMediaService

        existing = self._existing()
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = _svc(2, app_id=99)
        with patch.object(PlaygroundMediaService, "get_temp_repository", return_value=existing), patch(
            AI_REPO, return_value=_svc(2, app_id=99)
        ):
            with pytest.raises(ValidationError):
                PlaygroundMediaService.get_or_create_temp_repository(
                    10, 1, "s", db, transcription_service_id=2
                )
        assert existing.silo.transcription_service_id == 1
        db.commit.assert_not_called()

    def test_own_transcription_service_applied(self):
        from services.playground_media_service import PlaygroundMediaService

        existing = self._existing()
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = _svc(2)
        with patch.object(PlaygroundMediaService, "get_temp_repository", return_value=existing), patch(
            AI_REPO, return_value=_svc(2)
        ):
            PlaygroundMediaService.get_or_create_temp_repository(10, 1, "s", db, transcription_service_id=2)
        assert existing.silo.transcription_service_id == 2
        db.commit.assert_called_once()


class TestSiloCreationEmbeddingOwnership:
    def test_creation_with_foreign_embedding_rejected_nothing_persisted(self):
        foreign = _svc(7, app_id=99)
        foreign.name = "SECRET-NAME"
        db = _db()
        with patch("services.tier_enforcement_service.TierEnforcementService.check_resource_limit"), patch(
            "services.silo_service.SiloRepository.get_embedding_service_by_id", return_value=foreign
        ):
            with pytest.raises(ValidationError) as exc:
                SiloService.create_or_update_silo(_silo_data(silo_id=0, embedding_service_id=7), db=db)
        assert GENERIC in str(exc.value)
        assert "SECRET-NAME" not in str(exc.value)
        db.add.assert_not_called()
        db.commit.assert_not_called()


class TestRepositoryDeleteOwnership:
    def test_cross_app_delete_returns_404_and_does_not_delete(self):
        import asyncio
        from fastapi import HTTPException
        from routers.internal import repositories as repo_router
        from routers.controls import repository_scope

        foreign = MagicMock()
        foreign.app_id = 99
        with patch.object(repo_router.RepositoryService, "get_repository", return_value=foreign), patch.object(
            repo_router.RepositoryService, "delete_repository_router"
        ) as delete:
            with pytest.raises(HTTPException) as exc:
                repository_scope.require_repository_in_app(10, 5, MagicMock(), MagicMock())
        assert exc.value.status_code == 404
        delete.assert_not_called()

    def test_own_app_delete_proceeds(self):
        import asyncio
        from routers.internal import repositories as repo_router
        from routers.controls import repository_scope

        own = MagicMock()
        own.app_id = 10
        with patch.object(repo_router.RepositoryService, "get_repository", return_value=own), patch.object(
            repo_router.RepositoryService, "delete_repository_router"
        ) as delete:
            repository_scope.require_repository_in_app(10, 5, MagicMock(), MagicMock())
            asyncio.run(repo_router.delete_repository(10, 5, MagicMock(), MagicMock(), MagicMock()))
        delete.assert_called_once()
