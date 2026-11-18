"""Database-backed queries for a user's SCIM-provisioned group memberships."""

import pytest

from models.external_group import ExternalGroup
from models.external_group_membership import ExternalGroupMembership
from models.provisioning_connection import ProvisioningConnection
from models.user_external_identity import UserExternalIdentity
from repositories.my_groups_repository import MyGroupsRepository

pytestmark = pytest.mark.integration


class TestMyGroupsRepository:
    def test_lists_active_membership_without_active_app_access_rules(
        self, db, fake_user
    ):
        connection = ProvisioningConnection(
            provider_type="test",
            external_directory_id="my-groups-directory",
            connection_key="my-groups-no-access-rule",
            display_name="My Groups test connection",
            auth_mode="bearer",
            credential_hash="test-credential-hash",
            is_active=True,
        )
        db.add(connection)
        db.flush()

        identity = UserExternalIdentity(
            user_id=fake_user.user_id,
            connection_id=connection.id,
            external_id="my-groups-user",
            scim_id="my-groups-user-scim-id",
            user_name=fake_user.email,
            is_active=True,
        )
        group = ExternalGroup(
            connection_id=connection.id,
            external_id="my-groups-group",
            scim_id="my-groups-group-scim-id",
            display_name="Provisioned group without app access",
            is_active=True,
        )
        db.add_all([identity, group])
        db.flush()
        db.add(
            ExternalGroupMembership(
                group_id=group.id,
                user_external_identity_id=identity.id,
            )
        )
        db.flush()

        groups, total = MyGroupsRepository.list_groups(
            db, fake_user.user_id, offset=0, limit=20
        )
        group_apps = MyGroupsRepository.list_group_apps(
            db, fake_user.user_id, group.id, offset=0, limit=20
        )

        assert groups == [(group.id, group.display_name)]
        assert total == 1
        assert group_apps == (group.display_name, [], 0)
