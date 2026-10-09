"""Exercise the content-mode migration on an isolated legacy schema."""

import importlib.util
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations


path = Path(__file__).resolve().parents[3] / "alembic/versions/periodic008_channel_content_mode.py"
spec = importlib.util.spec_from_file_location("channel_content_migration", path)
migration = importlib.util.module_from_spec(spec)
spec.loader.exec_module(migration)


@pytest.fixture
def legacy_connection():
    engine = sa.create_engine("sqlite://")
    metadata = sa.MetaData()
    destinations = sa.Table("output_destination", metadata,
        sa.Column("id", sa.Integer, primary_key=True), sa.Column("app_id", sa.Integer),
        sa.Column("name", sa.String(255)), sa.Column("provider_key", sa.String),
        sa.Column("webhook_url", sa.String), sa.Column("credentials", sa.JSON),
        sa.Column("public_config", sa.JSON), sa.Column("enabled", sa.Boolean),
        sa.UniqueConstraint("app_id", "name"),
    )
    bindings = sa.Table("scheduled_task_output_binding", metadata,
        sa.Column("id", sa.Integer, primary_key=True), sa.Column("destination_id", sa.Integer),
        sa.Column("scheduled_task_id", sa.Integer), sa.Column("content_mode", sa.String),
        sa.Column("enabled", sa.Boolean),
    )
    deliveries = sa.Table("output_delivery", metadata,
        sa.Column("id", sa.Integer, primary_key=True), sa.Column("binding_id", sa.Integer),
        sa.Column("destination_id", sa.Integer), sa.Column("payload", sa.JSON),
        sa.Column("destination_snapshot", sa.JSON), sa.Column("status", sa.String),
    )
    metadata.create_all(engine)
    with engine.begin() as connection:
        common = {"app_id": 1, "provider_key": "webhook", "webhook_url": "https://example.com?secret=stored",
                  "credentials": {"bearer_token": "stored-token"}, "public_config": {"auth_mode": "bearer", "include_attachments": True}, "enabled": True}
        connection.execute(destinations.insert(), [
            {**common, "id": 1, "name": "Alerts"},
            {**common, "id": 2, "name": "Alerts (Extracto)"},
            {**common, "id": 3, "name": "x" * 255},
            {**common, "id": 4, "name": "Unused"},
            {**common, "id": 5, "name": "Excerpt only"},
        ])
        connection.execute(bindings.insert(), [
            {"id": index, "destination_id": destination_id, "scheduled_task_id": index,
             "content_mode": mode, "enabled": enabled}
            for index, destination_id, mode, enabled in [
                (1, 1, "result", True), (2, 1, "excerpt", True), (3, 1, "link_only", True),
                (4, 3, "result", True), (5, 3, "excerpt", False), (6, 5, "excerpt", True),
            ]
        ])
        connection.execute(deliveries.insert(), [
            {"id": 1, "binding_id": 2, "destination_id": 1, "payload": {"text": "prepared"},
             "destination_snapshot": {"name": "Alerts", "include_attachments": True}, "status": "pending"},
            {"id": 2, "binding_id": 3, "destination_id": None, "payload": {"text": "archived"},
             "destination_snapshot": {"name": "Deleted"}, "status": "accepted"},
        ])
        yield connection
    engine.dispose()


def apply(connection, direction):
    with Operations.context(MigrationContext.configure(connection)):
        getattr(migration, direction)()


def table(connection, name):
    return sa.Table(name, sa.MetaData(), autoload_with=connection)


def test_upgrade_preserves_modes_bindings_credentials_and_prepared_deliveries(legacy_connection):
    connection = legacy_connection
    apply(connection, "upgrade")
    destinations = table(connection, "output_destination")
    bindings = table(connection, "scheduled_task_output_binding")
    deliveries = table(connection, "output_delivery")
    assert "content_mode" not in bindings.c
    channels = {row.id: row._mapping for row in connection.execute(sa.select(destinations))}
    selected = {row.id: row._mapping for row in connection.execute(sa.select(bindings))}
    for binding_id, mode in {1: "result", 2: "excerpt", 3: "link_only", 4: "result", 5: "excerpt", 6: "excerpt"}.items():
        channel = channels[selected[binding_id]["destination_id"]]
        assert channel["content_mode"] == mode
        assert channel["webhook_url"] == "https://example.com?secret=stored"
        assert channel["credentials"] == {"bearer_token": "stored-token"}
        assert channel["public_config"] == {"auth_mode": "bearer", "include_attachments": True}
    assert selected[1]["destination_id"] == 1
    assert channels[selected[2]["destination_id"]]["name"] == "Alerts (Extracto 2)"
    assert len(channels[selected[5]["destination_id"]]["name"]) <= 255
    assert selected[5]["enabled"] is False
    assert channels[4]["content_mode"] == "result"
    assert channels[5]["content_mode"] == "excerpt"
    prepared = connection.execute(sa.select(deliveries).where(deliveries.c.id == 1)).mappings().one()
    assert prepared["destination_id"] == selected[2]["destination_id"]
    assert prepared["payload"] == {"text": "prepared"}
    assert prepared["destination_snapshot"] == {"name": "Alerts", "include_attachments": True}
    assert prepared["status"] == "pending"
    assert connection.execute(sa.select(deliveries.c.destination_id).where(deliveries.c.id == 2)).scalar_one() is None


def test_downgrade_restores_per_task_modes_and_retains_channel_variants(legacy_connection):
    connection = legacy_connection
    apply(connection, "upgrade")
    apply(connection, "downgrade")
    destinations = table(connection, "output_destination")
    bindings = table(connection, "scheduled_task_output_binding")
    assert "content_mode" not in destinations.c
    modes = dict(connection.execute(sa.select(bindings.c.id, bindings.c.content_mode)).all())
    assert modes == {1: "result", 2: "excerpt", 3: "link_only", 4: "result", 5: "excerpt", 6: "excerpt"}
    assert connection.execute(sa.select(sa.func.count()).select_from(destinations)).scalar_one() == 8
