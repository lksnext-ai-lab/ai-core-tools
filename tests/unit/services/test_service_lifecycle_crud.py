"""Lifecycle fields in AI / embedding service CRUD helpers, copy and export/import (no DB)."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from schemas.ai_service_schemas import CreateUpdateAIServiceSchema
from schemas.embedding_service_schemas import CreateUpdateEmbeddingServiceSchema
from schemas.export_schemas import (
    AIServiceExportFileSchema,
    EmbeddingServiceExportFileSchema,
    ExportAIServiceSchema,
    ExportEmbeddingServiceSchema,
    ExportMetadataSchema,
)
from services.ai_service_export_service import AIServiceExportService
from services.ai_service_import_service import AIServiceImportService
from services.ai_service_service import AIServiceService
from services.embedding_service_export_service import EmbeddingServiceExportService
from services.embedding_service_import_service import EmbeddingServiceImportService
from services.embedding_service_service import EmbeddingServiceService
from schemas.import_schemas import ConflictMode
from schemas.service_lifecycle_schemas import ServiceLifecycleFieldsMixin

FUTURE = datetime.now(timezone.utc) + timedelta(days=5)
PAST = datetime.now(timezone.utc) - timedelta(days=5)


def _svc(**over):
    base = dict(
        service_id=7, app_id=3, name="svc", provider="OpenAI", description="gpt", api_key="sk-abcdef1234",
        endpoint="http://x", api_version=None, supports_video=False, create_date=datetime.now(),
        extra_config=None, last_error=None, last_error_at=None,
        end_of_service_at=None, deprecation_notice=None,
    )
    base.update(over)
    return SimpleNamespace(**base)


class _Update(ServiceLifecycleFieldsMixin):
    """Payload whose lifecycle fields may be absent (tracked via model_fields_set)."""


def _Payload(eos, notice):
    return _Update(end_of_service_at=eos, deprecation_notice=notice)


SERVICES = [AIServiceService, EmbeddingServiceService]


@pytest.mark.parametrize("cls", SERVICES)
class TestMapping:
    def test_list_item_fields(self, cls):
        item = cls._to_list_item(_svc(end_of_service_at=FUTURE, deprecation_notice="n"), warning_days=30)
        assert item.lifecycle_status == "deprecated"
        assert item.deprecation_notice == "n"
        assert item.end_of_service_at == FUTURE

    def test_list_item_defaults_active(self, cls):
        item = cls._to_list_item(_svc(), warning_days=30)
        assert item.lifecycle_status == "active"
        assert item.end_of_service_at is None

    def test_list_item_retired(self, cls):
        assert cls._to_list_item(_svc(end_of_service_at=PAST), warning_days=30).lifecycle_status == "retired"

    def test_detail_fields_and_masking(self, cls):
        d = cls.to_detail(_svc(end_of_service_at=PAST, deprecation_notice="n"), 30)
        assert d.lifecycle_status == "retired"
        assert d.deprecation_notice == "n"
        assert d.api_key == "****1234"
        assert d.base_url == "http://x"
        assert d.available_providers == []

    def test_detail_active_beyond_window(self, cls):
        d = cls.to_detail(_svc(end_of_service_at=FUTURE), 3, providers=[{"value": "a", "name": "a"}])
        assert d.lifecycle_status == "active"
        assert d.available_providers == [{"value": "a", "name": "a"}]

    def test_apply_logs_only_when_date_changes(self, cls):
        svc = _svc()
        with patch("services.service_lifecycle_service.logger") as log:
            cls.apply_lifecycle_fields(svc, _Payload(FUTURE, "note"), actor_id=9)
            assert log.info.call_count == 1
            assert log.info.call_args[0][0].startswith("service_lifecycle.updated")
            assert 9 in log.info.call_args[0]
            assert svc.end_of_service_at == FUTURE and svc.deprecation_notice == "note"

            cls.apply_lifecycle_fields(svc, _Payload(FUTURE, "other note"), actor_id=9)
            assert log.info.call_count == 1
            assert svc.deprecation_notice == "other note"

            cls.apply_lifecycle_fields(svc, _Payload(None, None), actor_id=9)
            assert log.info.call_count == 2
            assert svc.end_of_service_at is None

    def test_no_log_when_service_not_persisted(self, cls):
        svc = _svc(service_id=None)
        with patch("services.service_lifecycle_service.logger") as log:
            cls.apply_lifecycle_fields(svc, _Payload(FUTURE, None), actor_id=9)
        log.info.assert_not_called()
        assert svc.end_of_service_at == FUTURE

    def test_update_without_fields_keeps_existing(self, cls):
        svc = _svc(end_of_service_at=FUTURE, deprecation_notice="keep")
        cls.apply_lifecycle_fields(svc, _Update(), actor_id=1)
        assert svc.end_of_service_at == FUTURE
        assert svc.deprecation_notice == "keep"

    def test_explicit_null_clears(self, cls):
        svc = _svc(end_of_service_at=FUTURE, deprecation_notice="x")
        cls.apply_lifecycle_fields(svc, _Update(end_of_service_at=None, deprecation_notice=None), actor_id=1)
        assert svc.end_of_service_at is None
        assert svc.deprecation_notice is None


@pytest.mark.parametrize("repo_path,cls", [
    ("services.ai_service_service.AIServiceRepository", AIServiceService),
    ("services.embedding_service_service.EmbeddingServiceRepository", EmbeddingServiceService),
])
def test_list_reads_warning_days_once(repo_path, cls):
    repo = MagicMock()
    repo.get_by_app_id.return_value = [_svc(), _svc(service_id=8)]
    repo.get_system_services.return_value = [_svc(service_id=9)]
    fn = cls.get_ai_services_by_app_id if cls is AIServiceService else cls.get_embedding_services_list
    mod = cls.__module__
    with patch(repo_path, repo), patch(f"{mod}.ServiceLifecycleService.warning_days", return_value=30) as wd:
        result = fn(MagicMock(), 3)
    assert len(result) == 3
    wd.assert_called_once()


def test_create_ai_sets_lifecycle_fields():
    created = {}
    data = CreateUpdateAIServiceSchema(
        name="n", provider="OpenAI", model_name="m", api_key="k",
        end_of_service_at="2030-01-01T00:00:00Z", deprecation_notice=" bye ",
    )

    def _create(db, svc):
        created["svc"] = svc
        svc.service_id = 1
        return svc

    with patch("services.ai_service_service.AIServiceRepository.create", side_effect=_create), \
            patch("services.ai_service_service.AIServiceService.get_ai_service_detail", return_value="detail"), \
            patch("models.app.App"), patch("services.tier_enforcement_service.TierEnforcementService"):
        db = MagicMock()
        assert AIServiceService.create_or_update_ai_service(db, 3, 0, data, actor_id=4) == "detail"
    assert created["svc"].end_of_service_at == datetime(2030, 1, 1, tzinfo=timezone.utc)
    assert created["svc"].deprecation_notice == "bye"


def test_create_embedding_sets_lifecycle_fields():
    data = CreateUpdateEmbeddingServiceSchema(
        name="n", provider="OpenAI", model_name="m", api_key="k",
        end_of_service_at="2030-01-01T00:00:00Z", deprecation_notice="x",
    )

    def _create(db, svc):
        svc.service_id = 1
        return svc

    with patch("services.embedding_service_service.EmbeddingServiceRepository.create", side_effect=_create):
        svc = EmbeddingServiceService.create_or_update_embedding_service(MagicMock(), 3, 0, data, actor_id=4)
    assert svc.end_of_service_at == datetime(2030, 1, 1, tzinfo=timezone.utc)
    assert svc.deprecation_notice == "x"


def test_copy_ai_service_leaves_lifecycle_unset():
    src = _svc(end_of_service_at=PAST, deprecation_notice="old")
    captured = {}

    def _create(db, svc):
        captured["svc"] = svc
        svc.service_id = 2
        return svc

    with patch("services.ai_service_service.AIServiceRepository.get_by_id_and_app_id", return_value=src), \
            patch("services.ai_service_service.AIServiceService.get_ai_services_by_app_id", return_value=[]), \
            patch("services.ai_service_service.AIServiceRepository.create", side_effect=_create), \
            patch("services.ai_service_service.AIServiceService.get_ai_service_detail", return_value="d"):
        AIServiceService.copy_ai_service(MagicMock(), 3, 7)
    assert captured["svc"].end_of_service_at is None
    assert captured["svc"].deprecation_notice is None


# ---------------- export / import ----------------

def test_export_ai_includes_fields():
    svc = _svc(end_of_service_at=FUTURE, deprecation_notice="n")
    exp = AIServiceExportService(MagicMock())
    exp.ai_service_repo = MagicMock()
    exp.ai_service_repo.get_by_id_and_app_id.return_value = svc
    out = exp.export_ai_service(7, 3)
    assert out.ai_service.end_of_service_at == FUTURE
    assert out.ai_service.deprecation_notice == "n"


def test_export_embedding_includes_fields():
    svc = _svc(end_of_service_at=FUTURE, deprecation_notice="n")
    exp = EmbeddingServiceExportService(MagicMock())
    exp.embedding_service_repo = MagicMock()
    exp.embedding_service_repo.get_by_id_and_app_id.return_value = svc
    out = exp.export_embedding_service(7, 3)
    assert out.embedding_service.end_of_service_at == FUTURE
    assert out.embedding_service.deprecation_notice == "n"


def _refresh(obj):
    if getattr(obj, "service_id", None) is None:
        obj.service_id = 99


@pytest.mark.parametrize("imp_cls,file_cls,exp_cls,attr", [
    (AIServiceImportService, AIServiceExportFileSchema, ExportAIServiceSchema, "ai_service"),
    (EmbeddingServiceImportService, EmbeddingServiceExportFileSchema, ExportEmbeddingServiceSchema,
     "embedding_service"),
])
class TestImport:
    def _file(self, file_cls, exp_cls, attr):
        payload = exp_cls(name="svc", provider="OpenAI", model_name="m",
                          end_of_service_at=PAST, deprecation_notice="gone")
        return file_cls(metadata=ExportMetadataSchema(), **{attr: payload})

    def test_create_sets_fields(self, imp_cls, file_cls, exp_cls, attr):
        session = MagicMock()
        session.refresh.side_effect = _refresh
        imp = imp_cls(session)
        data = self._file(file_cls, exp_cls, attr)
        with patch.object(imp, "validate_import", return_value=SimpleNamespace(has_conflict=False)), \
                patch.object(imp, "get_by_name_and_app", return_value=None):
            getattr(imp, f"import_{attr}")(data, 3, conflict_mode=ConflictMode.FAIL)
        added = session.add.call_args[0][0]
        assert added.end_of_service_at == PAST
        assert added.deprecation_notice == "gone"

    def test_override_sets_fields(self, imp_cls, file_cls, exp_cls, attr):
        session = MagicMock()
        existing = _svc(end_of_service_at=None)
        imp = imp_cls(session)
        data = self._file(file_cls, exp_cls, attr)
        with patch.object(imp, "validate_import", return_value=SimpleNamespace(has_conflict=True)), \
                patch.object(imp, "get_by_name_and_app", return_value=existing):
            getattr(imp, f"import_{attr}")(data, 3, conflict_mode=ConflictMode.OVERRIDE)
        assert existing.end_of_service_at == PAST
        assert existing.deprecation_notice == "gone"


def test_update_ai_without_fields_keeps_date():
    existing = _svc(end_of_service_at=FUTURE, deprecation_notice="keep")
    data = CreateUpdateAIServiceSchema(name="n", provider="OpenAI", model_name="m", api_key="k")
    with patch("services.ai_service_service.AIServiceRepository.get_by_id_and_app_id", return_value=existing), \
            patch("services.ai_service_service.AIServiceRepository.update", side_effect=lambda db, s: s), \
            patch("services.ai_service_service.AIServiceService.get_ai_service_detail", return_value="d"):
        AIServiceService.create_or_update_ai_service(MagicMock(), 3, 7, data, actor_id=1)
    assert existing.end_of_service_at == FUTURE
    assert existing.deprecation_notice == "keep"


def test_update_embedding_explicit_null_clears_date():
    existing = _svc(end_of_service_at=FUTURE, deprecation_notice="x")
    data = CreateUpdateEmbeddingServiceSchema(
        name="n", provider="OpenAI", model_name="m", api_key="k", end_of_service_at=None
    )
    with patch(
        "services.embedding_service_service.EmbeddingServiceRepository.get_by_id_and_app_id", return_value=existing
    ), patch("services.embedding_service_service.EmbeddingServiceRepository.update", side_effect=lambda db, s: s):
        EmbeddingServiceService.create_or_update_embedding_service(MagicMock(), 3, 7, data, actor_id=1)
    assert existing.end_of_service_at is None
    assert existing.deprecation_notice == "x"
