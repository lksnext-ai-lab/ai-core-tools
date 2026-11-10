"""CB-2: empty credentials are persisted as None; {} and None read identically (FR-14, AC-20, AC-21)."""

import json
import re

import pytest
from connectors import registry as connector_registry
from connectors.core.settings import normalize_credentials, read_credentials
from models.output_delivery import OutputDelivery, OutputDestination
from services.output_channels import destination_test, destinations
from services.output_channels.delivery_factory import create_deliveries_for_run
from services.output_channels.delivery_processor import process_delivery
from services.output_channels.dto import destination_dto
from sqlalchemy import event

from .factories import HMAC_SECRET, TEAMS_URL, WEBHOOK_URL, make_destination
from .golden import conftest as golden_fixtures
from .golden.golden_support import bind, make_task_and_run

# Shared fixtures of the golden harness (same recorder / deterministic ids), re-exported for this module.
deterministic = golden_fixtures.deterministic
golden_outbox = golden_fixtures.golden_outbox
http_recorder = golden_fixtures.http_recorder

NONE_CONFIG = {"auth_mode": "none"}
HMAC_CONFIG = {"auth_mode": "hmac_sha256"}


@pytest.fixture
def db(outbox):
    with outbox() as session:
        yield session


def _create(db, **kwargs):
    values = {"app_id": 1, "created_by": 1, "name": "d", "webhook_url": TEAMS_URL} | kwargs
    return destinations.create_destination(db, **values)


def _webhook(db, name, credentials, config=None):
    return _create(db, name=name, provider_key="webhook", webhook_url=WEBHOOK_URL,
                   public_config=config or NONE_CONFIG, credentials=credentials)


class TestHelpers:
    @pytest.mark.parametrize("value", [None, {}])
    def test_empty_values(self, value):
        assert read_credentials(value) == {}
        assert normalize_credentials(value) is None

    def test_non_empty_is_copied(self):
        source = {"bearer_token": "t"}
        assert normalize_credentials(source) == source and normalize_credentials(source) is not source
        assert read_credentials(source) == source and read_credentials(source) is not source


class TestCreate:
    @pytest.mark.parametrize("credentials", [None, {}])
    def test_teams_empty_is_none(self, db, credentials):
        assert _create(db, credentials=credentials).credentials is None

    @pytest.mark.parametrize("credentials", [None, {}])
    def test_webhook_none_mode_empty_is_none(self, db, credentials):
        assert _webhook(db, "w", credentials).credentials is None

    def test_hmac_credentials_are_stored_as_given(self, db):
        row = _webhook(db, "h", {"signing_secret": HMAC_SECRET}, HMAC_CONFIG)
        assert row.credentials == {"signing_secret": HMAC_SECRET}


class TestPatch:
    def test_name_only_patch_keeps_legacy_empty_dict(self, db):
        row = make_destination(1, provider_key="webhook", config=NONE_CONFIG, credentials={})
        db.add(row)
        db.commit()
        writes = _record_credential_writes()
        destinations.update_destination(db, row, {"name": "renamed"})
        assert row.credentials == {}
        assert writes == []

    def test_clear_credentials_writes_none(self, db):
        row = _webhook(db, "h", {"signing_secret": HMAC_SECRET}, HMAC_CONFIG)
        destinations.update_destination(db, row, {"public_config": NONE_CONFIG, "clear_credentials": True})
        assert row.credentials is None

    def test_clear_credentials_on_empty_dict_row_writes_none(self, db):
        row = make_destination(1, provider_key="webhook", config=NONE_CONFIG, credentials={})
        db.add(row)
        db.commit()
        destinations.update_destination(db, row, {"clear_credentials": True})
        assert row.credentials is None

    def test_new_credentials_are_written(self, db):
        row = _webhook(db, "n", None)
        destinations.update_destination(
            db, row, {"public_config": HMAC_CONFIG, "credentials": {"signing_secret": HMAC_SECRET}})
        assert row.credentials == {"signing_secret": HMAC_SECRET}

    def test_patch_without_credentials_does_not_lose_them(self, db):
        row = _webhook(db, "k", {"signing_secret": HMAC_SECRET}, HMAC_CONFIG)
        destinations.update_destination(db, row, {"name": "k2", "enabled": False})
        assert row.credentials == {"signing_secret": HMAC_SECRET}

    @pytest.mark.parametrize("config", [{"auth_mode": "none"}, {"auth_mode": "bearer"}])
    def test_changing_auth_mode_without_credentials_is_rejected_atomically(self, db, config):
        row = _webhook(db, "h", {"signing_secret": HMAC_SECRET}, HMAC_CONFIG)
        before = (row.name, row.public_config, row.credentials, row.webhook_url)
        with pytest.raises(ValueError) as caught:
            destinations.update_destination(db, row, {"public_config": config})
        assert HMAC_SECRET not in str(caught.value)
        assert not db.dirty
        assert db.get(OutputDestination, row.id) is row
        assert (row.name, row.public_config, row.credentials, row.webhook_url) == before
        assert HMAC_SECRET not in json.dumps(destination_dto(row), default=str)
        if config["auth_mode"] == "none":
            assert str(caught.value) == "Authentication mode none does not accept credentials"

    def test_teams_name_patch_keeps_legacy_empty_dict(self, db):
        row = make_destination(1, credentials={})
        db.add(row)
        db.commit()
        writes = _record_credential_writes()
        destinations.update_destination(db, row, {"name": "renamed"})
        assert row.credentials == {}
        assert writes == []


def _record_credential_writes():
    """Record every ORM-level assignment to ``OutputDestination.credentials`` (even same-value ones)."""
    writes = []

    def on_set(target, value, old, initiator):
        writes.append(value)

    event.listen(OutputDestination.credentials, "set", on_set)
    _LISTENERS.append(on_set)
    return writes


_LISTENERS = []


@pytest.fixture(autouse=True)
def _remove_listeners():
    yield
    while _LISTENERS:
        event.remove(OutputDestination.credentials, "set", _LISTENERS.pop())


class TestEquivalentReads:
    @pytest.mark.parametrize("provider_key,config", [("teams_workflow", {}), ("webhook", NONE_CONFIG)])
    def test_dto_and_has_credentials(self, provider_key, config):
        legacy = destination_dto(make_destination(1, provider_key=provider_key, config=config, credentials={}))
        normalized = destination_dto(make_destination(1, provider_key=provider_key, config=config, credentials=None))
        assert legacy == normalized
        assert legacy["has_credentials"] is False

    @pytest.mark.asyncio
    @pytest.mark.parametrize("provider_key,config", [("teams_workflow", {}), ("webhook", NONE_CONFIG)])
    async def test_test_destination_sends_the_same_request(self, monkeypatch, provider_key, config):
        real = connector_registry.get_output_provider(provider_key)
        sent = []

        class Proxy:
            def __getattr__(self, name):
                return getattr(real, name)

            async def send(self, request):
                sent.append(request)
                return {"http_status": 202}

        monkeypatch.setattr(connector_registry, "get_output_provider", lambda key: Proxy())
        for credentials in ({}, None):
            row = make_destination(1, provider_key=provider_key, config=config, credentials=credentials)
            await destination_test.test_destination(row)
        legacy, normalized = sent
        assert legacy.credentials == normalized.credentials == {}
        assert (legacy.url, legacy.public_config, legacy.content_type) == (
            normalized.url, normalized.public_config, normalized.content_type)
        assert _volatile_free(legacy) == _volatile_free(normalized)


def _volatile_free(request):
    """Payload and body as JSON text with the per-call event id / timestamps blanked out."""
    def clean(value):
        text = json.dumps(value, sort_keys=True)
        text = re.sub(r"\d{4}-\d\d-\d\dT[\d:.]+(?:\+00:00|Z)", "<ts>", text)
        return re.sub(r'"event_id": "[^"]*"', '"event_id": "<id>"', text)

    body = json.loads(request.body) if request.body else None
    return clean(request.payload), clean(body)


# --- {} vs None through the real send path (http_recorder), deliveries and connection test --------------------------

CASES = [
    pytest.param("teams_workflow", {}, id="teams"),
    pytest.param("webhook", NONE_CONFIG, id="webhook-none"),
]


def _raw_row(db, provider_key, config, name, credentials):
    """Insert a destination bypassing the service, so a legacy ``{}`` can be stored."""
    row = OutputDestination(
        app_id=1, created_by=1, name=name, provider_key=provider_key, content_mode="result",
        public_config=dict(config), credentials=credentials,
        webhook_url=TEAMS_URL if provider_key == "teams_workflow" else WEBHOOK_URL,
    )
    db.add(row)
    db.commit()
    return row


def _normalized_request(request: dict) -> dict:
    """Recorded request with the per-call event ids / idempotency keys / timestamps blanked out."""
    text = request["body"].decode("utf-8")
    text = re.sub(r"\d{4}-\d\d-\d\dT[\d:.]+(?:\+00:00|Z)", "<ts>", text)
    text = re.sub(r"dest-\d", "dest-N", text)
    text = re.sub(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", "<id>", text)
    headers = {k: re.sub(r"[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}", "<id>", v) for k, v in request["headers"].items()}
    return {**request, "body": text, "headers": {**headers, "content-length": "<len>"}}


@pytest.mark.usefixtures("deterministic")
class TestEquivalentThroughRealSendPath:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("provider_key,config", CASES)
    async def test_process_delivery(self, golden_outbox, http_recorder, provider_key, config):
        db = golden_outbox()
        try:
            task, run = make_task_and_run(db, output_text="Done.", output_files=[])
            rows = [_raw_row(db, provider_key, config, f"dest-{i}", credentials)
                    for i, credentials in enumerate(({}, None))]
            for row in rows:
                bind(db, row)
            create_deliveries_for_run(db, task=task, run=run)
            db.commit()
            deliveries = db.query(OutputDelivery).order_by(OutputDelivery.id).all()
            assert len(deliveries) == 2
            for delivery in deliveries:
                await process_delivery(delivery.id, 0)
            db.expire_all()
            legacy, normalized = db.query(OutputDelivery).order_by(OutputDelivery.id).all()
            assert (legacy.status, normalized.status) == ("accepted", "accepted")
            snapshots = [{k: v for k, v in d.destination_snapshot.items() if k not in ("id", "name")}
                         for d in (legacy, normalized)]
            assert snapshots[0] == snapshots[1]
            assert len(http_recorder.requests) == 2
            first, second = (_normalized_request(r) for r in http_recorder.requests)
            assert first == second
        finally:
            db.close()

    @pytest.mark.asyncio
    @pytest.mark.parametrize("provider_key,config", CASES)
    async def test_connection_test(self, golden_outbox, http_recorder, provider_key, config):
        db = golden_outbox()
        try:
            for index, credentials in enumerate(({}, None)):
                row = _raw_row(db, provider_key, config, f"dest-{index}", credentials)
                assert (await destination_test.test_destination(row))["http_status"] == 202
            assert len(http_recorder.requests) == 2
            first, second = (_normalized_request(r) for r in http_recorder.requests)
            assert first == second
        finally:
            db.close()
