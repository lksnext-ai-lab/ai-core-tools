"""CB-2 against PostgreSQL: empty credentials persist as None; legacy ``{}`` rows read the same (AC-20, AC-21)."""

import pytest
from connectors import registry as connector_registry
from connectors.core import http as core_http
from models.output_delivery import OutputDestination
from services.output_channels import destination_test, destinations
from services.output_channels.dto import destination_dto
from sqlalchemy import Text, cast, func, select

pytestmark = pytest.mark.integration

TEAMS_URL = "https://prod.logic.azure.com/workflows/abc/triggers/manual?sig=secret"
WEBHOOK_URL = "https://hooks.example.com/mattin"
NONE_CONFIG = {"auth_mode": "none"}


@pytest.fixture(autouse=True)
def _public_dns(monkeypatch):
    monkeypatch.setattr(core_http, "resolve_host", lambda host: ["20.1.2.3"])


def _create_teams(db, app, user, name, credentials):
    return destinations.create_destination(
        db, app_id=app.app_id, created_by=user.user_id, name=name, webhook_url=TEAMS_URL, credentials=credentials)


def _create_webhook(db, app, user, name, credentials):
    return destinations.create_destination(
        db, app_id=app.app_id, created_by=user.user_id, name=name, provider_key="webhook",
        webhook_url=WEBHOOK_URL, public_config=NONE_CONFIG, credentials=credentials)


def _raw(db, destination_id):
    """(JSON type, text) as PostgreSQL stores the column."""
    return db.execute(
        select(func.json_typeof(OutputDestination.credentials), cast(OutputDestination.credentials, Text))
        .where(OutputDestination.id == destination_id)
    ).one()


def _characterized_none_representation(db, app, name):
    """Physical form of a plain ``credentials = None`` assignment (see test_credentials_representation)."""
    row = OutputDestination(app_id=app.app_id, name=name, provider_key="webhook", webhook_url=WEBHOOK_URL)
    row.credentials = None
    db.add(row)
    db.flush()
    return _raw(db, row.id)


class TestCreatePersistsNone:
    @pytest.mark.parametrize("make", ["teams", "webhook"])
    @pytest.mark.parametrize("credentials", [{}, None])
    def test_empty_credentials(self, db, fake_app, fake_user, make, credentials):
        create = _create_teams if make == "teams" else _create_webhook
        row = create(db, fake_app, fake_user, f"{make}-{credentials}", credentials)
        db.expire_all()
        assert db.get(OutputDestination, row.id).credentials is None
        assert _raw(db, row.id) == _characterized_none_representation(db, fake_app, "reference-none")


class TestPatchClearsToNone:
    def test_clear_credentials(self, db, fake_app, fake_user):
        row = destinations.create_destination(
            db, app_id=fake_app.app_id, created_by=fake_user.user_id, name="hook", provider_key="webhook",
            webhook_url=WEBHOOK_URL,
            public_config={"auth_mode": "bearer"}, credentials={"bearer_token": "tok"})
        destinations.update_destination(db, row, {"public_config": NONE_CONFIG, "clear_credentials": True})
        db.expire_all()
        assert db.get(OutputDestination, row.id).credentials is None
        assert _raw(db, row.id) == _characterized_none_representation(db, fake_app, "reference-none")


def _legacy_row(db, app, user, name, provider_key, credentials):
    row = OutputDestination(
        app_id=app.app_id, created_by=user.user_id, name=name, provider_key=provider_key,
        webhook_url=TEAMS_URL if provider_key == "teams_workflow" else WEBHOOK_URL,
        public_config=NONE_CONFIG if provider_key == "webhook" else {}, credentials=credentials)
    db.add(row)
    db.flush()
    return row


@pytest.mark.parametrize("provider_key", ["teams_workflow", "webhook"])
class TestLegacyEmptyDictRows:
    def test_name_only_patch_keeps_empty_dict(self, db, fake_app, fake_user, provider_key):
        row = _legacy_row(db, fake_app, fake_user, "legacy", provider_key, {})
        destinations.update_destination(db, row, {"name": "renamed"})
        db.expire_all()
        assert db.get(OutputDestination, row.id).credentials == {}
        assert _raw(db, row.id)[1] == "{}"

    def test_reads_like_none(self, db, fake_app, fake_user, provider_key):
        legacy = _legacy_row(db, fake_app, fake_user, "legacy", provider_key, {})
        normalized = _legacy_row(db, fake_app, fake_user, "normalized", provider_key, None)
        dto_legacy, dto_norm = destination_dto(legacy), destination_dto(normalized)
        assert dto_legacy["has_credentials"] is dto_norm["has_credentials"] is False
        for key in ("id", "name", "created_at", "updated_at"):
            dto_legacy.pop(key), dto_norm.pop(key)
        assert dto_legacy == dto_norm

    @pytest.mark.asyncio
    async def test_connection_test_sends_the_same_request(self, db, fake_app, fake_user, provider_key, monkeypatch):
        real = connector_registry.get_output_provider(provider_key)
        sent = []

        class Proxy:
            def __getattr__(self, name):
                return getattr(real, name)

            async def send(self, request):
                sent.append(request)
                return {"http_status": 202}

        monkeypatch.setattr(connector_registry, "get_output_provider", lambda key: Proxy())
        for index, credentials in enumerate(({}, None)):
            await destination_test.test_destination(
                _legacy_row(db, fake_app, fake_user, f"c{index}", provider_key, credentials))
        legacy, normalized = sent
        assert legacy.credentials == normalized.credentials == {}
        assert (legacy.url, legacy.public_config, legacy.content_type) == (
            normalized.url, normalized.public_config, normalized.content_type)
