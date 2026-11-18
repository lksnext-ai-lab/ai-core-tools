"""Database-backed connection isolation for explicit group app-access policies."""

import pytest

from models.external_group import ExternalGroup
from models.group_app_access_rule import GroupAppAccessRole, GroupAppAccessRule
from models.provisioning_connection import ProvisioningConnection
from repositories.group_app_access_repository import GroupAppAccessRepository
from tests.factories import AppFactory, UserFactory, configure_factories

pytestmark = pytest.mark.integration


def _connection(db, key):
    connection = ProvisioningConnection(
        provider_type="test",
        external_directory_id=f"directory-{key}",
        connection_key=f"group-access-{key}",
        display_name=f"Connection {key}",
        auth_mode="bearer",
        credential_hash=f"hash-{key}",
        is_active=True,
    )
    db.add(connection)
    db.flush()
    return connection


def _group(db, connection, external_id, *, active=True):
    group = ExternalGroup(
        connection_id=connection.id,
        external_id=external_id,
        scim_id=f"scim-{external_id}",
        display_name=f"Group {external_id}",
        is_active=active,
    )
    db.add(group)
    db.flush()
    return group


def _rule(db, app, group, user):
    rule = GroupAppAccessRule(
        group_id=group.id,
        app_id=app.app_id,
        role=GroupAppAccessRole.VIEWER,
        created_by_user_id=user.user_id,
        is_active=True,
    )
    db.add(rule)
    db.flush()
    return rule


def _seed_two_connections(db):
    configure_factories(db)
    owner = UserFactory()
    app = AppFactory(owner=owner)
    first_connection = _connection(db, f"a-{owner.user_id}")
    other_connection = _connection(db, f"b-{owner.user_id}")
    first_group = _group(db, first_connection, f"a-{owner.user_id}")
    other_group = _group(db, other_connection, f"b-{owner.user_id}")
    _group(db, first_connection, f"inactive-{owner.user_id}", active=False)
    first_rule = _rule(db, app, first_group, owner)
    _rule(db, app, other_group, owner)
    return app, first_connection, first_group, other_group, first_rule


class TestGroupAppAccessRepositoryConnectionIsolation:
    def test_rule_listing_returns_only_rows_for_the_requested_connection(self, db):
        app, first_connection, first_group, other_group, first_rule = _seed_two_connections(
            db
        )

        rules = GroupAppAccessRepository.list_for_connection(
            db, app.app_id, first_connection.id, offset=0, limit=20
        )

        assert [rule.id for rule in rules] == [first_rule.id]
        assert [rule.group.id for rule in rules] == [first_group.id]
        assert all(rule.group.connection_id == first_connection.id for rule in rules)
        assert all(rule.group.id != other_group.id for rule in rules)

    def test_eligible_groups_exclude_other_connections_and_inactive_groups(self, db):
        app, first_connection, first_group, other_group, _ = _seed_two_connections(
            db
        )

        groups, total = GroupAppAccessRepository.list_eligible_groups(
            db, app.app_id, first_connection.id, offset=0, limit=20
        )

        assert [group.id for group in groups] == [first_group.id]
        assert total == 1
        assert all(group.connection_id == first_connection.id for group in groups)
        assert all(group.id != other_group.id for group in groups)
