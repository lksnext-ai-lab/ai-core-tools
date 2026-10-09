"""Unit tests for SystemOneServiceService (repository mocked: no database)."""
import json
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import ValidationError

from schemas.system_one_service_schemas import CreateUpdateSystemOneServiceSchema
from services import system_one_service_service as module
from services.system_one_service_service import ServiceInUseError, SystemOneServiceService


def _service(service_id=1, app_id=10, name="Nimble", endpoint="http://so.test", api_key="secret-token-1234",
             description="nimble-latest", extra_config='{"max_concurrency": 2}'):
    s = MagicMock()
    s.service_id, s.app_id, s.name, s.endpoint = service_id, app_id, name, endpoint
    s.api_key, s.description, s.extra_config = api_key, description, extra_config
    s.create_date = datetime(2026, 10, 9)
    return s


def _data(**kw):
    base = dict(name="Nimble", endpoint="http://so.test", api_key="tok", model="nimble-latest", max_concurrency=3)
    return CreateUpdateSystemOneServiceSchema(**{**base, **kw})


@pytest.fixture
def repo():
    with patch.object(module, "SystemOneServiceRepository") as r:
        r.create.side_effect = lambda db, s: _stamp(s)
        r.update.side_effect = lambda db, s: s
        yield r


def _stamp(s):
    s.service_id = s.service_id or 99
    return s


# ---------------------------------------------------------------- schema

def test_schema_validation_and_whitespace_trimming():
    d = _data(name="  Nimble  ", endpoint=" http://so.test/ ", api_key=" tok\n", model=" nimble-latest ")
    assert (d.name, d.endpoint, d.api_key, d.model) == ("Nimble", "http://so.test/", "tok", "nimble-latest")
    for bad in ({"max_concurrency": 0}, {"max_concurrency": 65}, {"name": ""}, {"name": "x" * 101}, {"model": ""}):
        with pytest.raises(ValidationError):
            _data(**bad)


# ----------------------------------------------------------------- create

def test_create_stores_fields_and_normalizes(repo):
    repo.get_by_id_and_app_id.return_value = None
    out = SystemOneServiceService.create_or_update_system_one_service(
        MagicMock(), 10, 0, _data(endpoint="http://so.test/", max_concurrency=2))
    saved = repo.create.call_args[0][1]
    assert saved.app_id == 10 and saved.name == "Nimble" and saved.endpoint == "http://so.test"
    assert saved.description == "nimble-latest" and saved.api_key == "tok"
    assert json.loads(saved.extra_config) == {"max_concurrency": 2}
    assert out.max_concurrency == 2 and out.model == "nimble-latest" and out.api_key.startswith("****")


def test_create_defaults_concurrency_when_missing(repo):
    SystemOneServiceService.create_or_update_system_one_service(MagicMock(), 10, 0, _data(max_concurrency=None))
    assert json.loads(repo.create.call_args[0][1].extra_config) == {"max_concurrency": 1}


@pytest.mark.parametrize("endpoint", ["ftp://x", "file:///etc/passwd", "so.test", "http://", "javascript:alert(1)"])
def test_create_rejects_non_http_endpoints(repo, endpoint):
    with pytest.raises(ValueError):
        SystemOneServiceService.create_or_update_system_one_service(MagicMock(), 10, 0, _data(endpoint=endpoint))
    repo.create.assert_not_called()


def test_private_addresses_are_allowed_by_design(repo):
    SystemOneServiceService.create_or_update_system_one_service(MagicMock(), 10, 0, _data(endpoint="http://172.16.59.1:8100"))
    assert repo.create.call_args[0][1].endpoint == "http://172.16.59.1:8100"


# ----------------------------------------------------------------- update

def test_update_with_masked_token_keeps_the_stored_one(repo):
    existing = _service(api_key="real-secret")
    repo.get_by_id_and_app_id.return_value = existing
    SystemOneServiceService.create_or_update_system_one_service(MagicMock(), 10, 1, _data(api_key="****cret"))
    assert existing.api_key == "real-secret"


def test_update_with_new_token_replaces_it_and_empty_clears_it(repo):
    existing = _service(api_key="old")
    repo.get_by_id_and_app_id.return_value = existing
    SystemOneServiceService.create_or_update_system_one_service(MagicMock(), 10, 1, _data(api_key="new"))
    assert existing.api_key == "new"
    SystemOneServiceService.create_or_update_system_one_service(MagicMock(), 10, 1, _data(api_key=""))
    assert existing.api_key is None


def test_update_of_unknown_service_returns_none(repo):
    repo.get_by_id_and_app_id.return_value = None
    assert SystemOneServiceService.create_or_update_system_one_service(MagicMock(), 10, 5, _data()) is None


# ------------------------------------------------------------ read / list

def test_detail_masks_token_and_reads_extra_config(repo):
    repo.get_by_id_and_app_id.return_value = _service()
    d = SystemOneServiceService.get_system_one_service_detail(MagicMock(), 10, 1)
    assert d.api_key == "****1234" and "secret-token" not in d.model_dump_json()
    assert (d.endpoint, d.model, d.max_concurrency) == ("http://so.test", "nimble-latest", 2)


def test_detail_of_new_service_has_defaults():
    d = SystemOneServiceService.get_system_one_service_detail(MagicMock(), 10, 0)
    assert d.service_id == 0 and d.model == "nimble-latest" and d.api_key == "" and d.max_concurrency == 1


def test_detail_tolerates_broken_extra_config(repo):
    repo.get_by_id_and_app_id.return_value = _service(extra_config="not json")
    assert SystemOneServiceService.get_system_one_service_detail(MagicMock(), 10, 1).max_concurrency == 1


def test_list_never_exposes_the_token(repo):
    repo.get_by_app_id.return_value = [_service(), _service(service_id=2, name="Other")]
    items = SystemOneServiceService.get_system_one_services_by_app_id(MagicMock(), 10)
    assert [i.name for i in items] == ["Nimble", "Other"]
    assert "secret-token" not in json.dumps([i.model_dump(mode="json") for i in items])


# ------------------------------------------------------------------- copy

def test_copy_uses_the_repo_convention_and_keeps_the_token(repo):
    repo.get_by_id_and_app_id.return_value = _service(api_key="tok")
    repo.get_by_app_id.return_value = [_service(name="Nimble"), _service(service_id=3, name="Nimble Copy")]
    SystemOneServiceService.copy_system_one_service(MagicMock(), 10, 1)
    copy = repo.create.call_args[0][1]
    assert copy.name == "Nimble Copy 2" and copy.api_key == "tok" and copy.app_id == 10
    assert copy.endpoint == "http://so.test" and copy.extra_config == '{"max_concurrency": 2}'


def test_copy_of_unknown_service_returns_none(repo):
    repo.get_by_id_and_app_id.return_value = None
    assert SystemOneServiceService.copy_system_one_service(MagicMock(), 10, 9) is None


# ----------------------------------------------------------------- delete

def test_delete_in_use_raises_with_the_agents_and_deletes_nothing(repo):
    repo.get_by_id_and_app_id.return_value = _service()
    a1, a2 = MagicMock(agent_id=5), MagicMock(agent_id=6)
    a1.name, a2.name = "Triage", "Validator"
    repo.get_agents_using.return_value = [a1, a2]
    with pytest.raises(ServiceInUseError) as e:
        SystemOneServiceService.delete_system_one_service(MagicMock(), 10, 1)
    assert e.value.agents == [{"agent_id": 5, "name": "Triage"}, {"agent_id": 6, "name": "Validator"}]
    repo.delete.assert_not_called()


def test_delete_free_service_and_missing_service(repo):
    repo.get_by_id_and_app_id.return_value = _service()
    repo.get_agents_using.return_value = []
    assert SystemOneServiceService.delete_system_one_service(MagicMock(), 10, 1) is True
    repo.delete.assert_called_once()
    repo.get_by_id_and_app_id.return_value = None
    assert SystemOneServiceService.delete_system_one_service(MagicMock(), 10, 2) is False


# ------------------------------------------------------- connection tests

@pytest.mark.asyncio
async def test_connection_with_config_maps_the_probe_result(repo):
    probe = AsyncMock(return_value={"ok": True, "message": "Connection successful",
                                    "models": ["nimble-latest"], "limits": {"max_concurrent_requests": 4}})
    with patch.object(module.system_one_client, "probe", probe):
        out = await SystemOneServiceService.test_connection_with_config(
            MagicMock(), 10, {"endpoint": "http://so.test", "api_key": "tok"})
    assert out == {"status": "success", "message": "Connection successful", "models": ["nimble-latest"],
                   "limits": {"max_concurrent_requests": 4}, "suggested_max_concurrency": 4}
    probe.assert_awaited_once_with("http://so.test", "tok")


@pytest.mark.asyncio
@pytest.mark.parametrize("workers,limits,expected", [
    ("8", {"max_concurrent_requests": 4}, 1),        # 4 slots shared by 8 processes: one each, retries absorb the rest
    ("2", {"max_concurrent_requests": 16}, 8),
    ("1", {"max_concurrent_requests": 4}, 4),
    ("8", None, None),                                # limits unknown: nothing to suggest
])
async def test_the_probe_suggests_a_per_process_concurrency(repo, monkeypatch, workers, limits, expected):
    monkeypatch.setenv("UVICORN_WORKERS", workers)
    probe = AsyncMock(return_value={"ok": True, "message": "ok", "models": [], "limits": limits})
    with patch.object(module.system_one_client, "probe", probe):
        out = await SystemOneServiceService.test_connection_with_config(MagicMock(), 10, {"endpoint": "http://so.test"})
    assert out["suggested_max_concurrency"] == expected


@pytest.mark.asyncio
async def test_a_failed_probe_suggests_nothing(repo):
    probe = AsyncMock(return_value={"ok": False, "message": "down", "models": [], "limits": None})
    with patch.object(module.system_one_client, "probe", probe):
        out = await SystemOneServiceService.test_connection_with_config(MagicMock(), 10, {"endpoint": "http://so.test"})
    assert out["suggested_max_concurrency"] is None


@pytest.mark.asyncio
@pytest.mark.parametrize("sent", ["", "****1234", None])
async def test_connection_recovers_the_stored_token_when_not_retyped(repo, sent):
    repo.get_by_id_and_app_id.return_value = _service(api_key="stored-token")
    probe = AsyncMock(return_value={"ok": True, "message": "ok", "models": [], "limits": None})
    with patch.object(module.system_one_client, "probe", probe):
        await SystemOneServiceService.test_connection_with_config(
            MagicMock(), 10, {"endpoint": "http://so.test", "api_key": sent}, service_id=1)
    probe.assert_awaited_once_with("http://so.test", "stored-token")


@pytest.mark.asyncio
async def test_connection_with_bad_url_is_an_error_result_not_an_exception(repo):
    out = await SystemOneServiceService.test_connection_with_config(MagicMock(), 10, {"endpoint": "ftp://x", "api_key": ""})
    assert out["status"] == "error" and "http" in out["message"]


@pytest.mark.asyncio
async def test_connection_failure_maps_to_error(repo):
    probe = AsyncMock(return_value={"ok": False, "message": "Cannot connect", "models": [], "limits": None})
    with patch.object(module.system_one_client, "probe", probe):
        out = await SystemOneServiceService.test_connection_with_config(
            MagicMock(), 10, {"endpoint": "http://so.test", "api_key": ""})
    assert out["status"] == "error" and out["message"] == "Cannot connect" and out["models"] == []


@pytest.mark.asyncio
async def test_saved_service_connection_test(repo):
    repo.get_by_id_and_app_id.return_value = _service()
    probe = AsyncMock(return_value={"ok": True, "message": "ok", "models": ["m"], "limits": None})
    with patch.object(module.system_one_client, "probe", probe):
        out = await SystemOneServiceService.test_connection(MagicMock(), 10, 1)
    assert out["status"] == "success"
    probe.assert_awaited_once_with("http://so.test", "secret-token-1234")
    repo.get_by_id_and_app_id.return_value = None
    assert await SystemOneServiceService.test_connection(MagicMock(), 10, 2) is None
