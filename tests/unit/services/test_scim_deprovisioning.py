from types import SimpleNamespace
from unittest.mock import MagicMock

from sqlalchemy.dialects import postgresql
from repositories.scim_user_repository import SCIMUserRepository
from schemas.scim_schemas import SCIMUserCreate, SCIMUserPatch, SCIMUserPatchOperation
from services.scim_service import SCIMService


def _identity():
    return SimpleNamespace(
        id=17,
        user_id=42,
        connection_id=3,
        external_id="source-user-17",
        scim_id="scim-user-17",
        is_active=True,
        user=SimpleNamespace(
            user_id=42,
            email="mattin-user@example.com",
            name="Mattin User",
            is_active=True,
        ),
        connection=SimpleNamespace(connection_key="connection-key"),
    )


def test_delete_user_deactivates_mattin_user_and_removes_external_identity():
    service = SCIMService()
    identity = _identity()
    service.user_repository = MagicMock()
    service.user_repository.get_by_scim_id.return_value = identity
    service._response = MagicMock(return_value="scim-response")
    db = MagicMock()

    service.delete_user(db, SimpleNamespace(id=3), identity.scim_id)

    assert identity.user.is_active is False
    service.user_repository.delete_external_data.assert_called_once_with(db, identity)
    db.commit.assert_called_once_with()


def test_patch_active_false_preserves_mattin_profile_and_removes_external_identity():
    service = SCIMService()
    identity = _identity()
    service.user_repository = MagicMock()
    service.user_repository.get_by_scim_id.return_value = identity
    service._response = MagicMock(return_value="scim-response")
    db = MagicMock()
    patch = SCIMUserPatch(
        Operations=[
            SCIMUserPatchOperation(op="replace", path="active", value=False),
            SCIMUserPatchOperation(op="replace", path="displayName", value="External Name"),
            SCIMUserPatchOperation(
                op="replace",
                path="emails",
                value=[{"value": "external@example.com", "type": "work"}],
            ),
        ]
    )

    response = service.patch_user(db, SimpleNamespace(id=3), identity.scim_id, patch)

    assert response == "scim-response"
    assert identity.user.is_active is False
    assert identity.user.name == "Mattin User"
    assert identity.user.email == "mattin-user@example.com"
    service.user_repository.delete_external_data.assert_called_once_with(db, identity)
    db.commit.assert_called_once_with()


def test_upsert_inactive_existing_user_preserves_mattin_profile_and_removes_identity():
    service = SCIMService()
    identity = _identity()
    service.user_repository = MagicMock()
    service.user_repository.get_by_external_id.return_value = identity
    service._response = MagicMock(return_value="scim-response")
    db = MagicMock()
    payload = SCIMUserCreate(
        externalId=identity.external_id,
        userName="external-user",
        active=False,
        displayName="External Name",
        emails=[{"value": "external@example.com", "type": "work"}],
    )

    response, created = service.upsert_user(db, SimpleNamespace(id=3), payload)

    assert response == "scim-response"
    assert created is False
    assert identity.user.is_active is False
    assert identity.user.name == "Mattin User"
    assert identity.user.email == "mattin-user@example.com"
    service.user_repository.delete_external_data.assert_called_once_with(db, identity)
    db.commit.assert_called_once_with()


def test_upsert_links_unique_unlinked_email_user():
    service = SCIMService()
    existing_user = SimpleNamespace(
        user_id=84,
        email="local-user@example.com",
        name="Local User",
        is_active=True,
    )
    service.user_repository = MagicMock()
    service.user_repository.get_by_external_id.return_value = None
    service.user_repository.get_oidc_linked_user.return_value = None
    service.user_repository.get_email_users.return_value = [existing_user]
    service.user_repository.get_external_identities_for_user.return_value = []
    service._response = MagicMock(return_value="scim-response")
    db = MagicMock()
    payload = SCIMUserCreate(
        externalId="source-user-84",
        userName="external-user",
        active=True,
        displayName="External Name",
        emails=[{"value": "local-user@example.com", "type": "work"}],
    )

    response, created = service.upsert_user(db, SimpleNamespace(id=3), payload)

    assert response == "scim-response"
    assert created is True
    assert existing_user.name == "External Name"
    assert existing_user.is_active is True
    identity = db.add.call_args.args[0]
    assert identity.user_id == existing_user.user_id
    assert identity.external_id == payload.externalId
    assert identity.is_active is True
    db.commit.assert_called_once_with()


def test_apply_patch_expands_root_object_into_user_attributes():
    identity = _identity()
    operation = SCIMUserPatchOperation(
        op="replace",
        value={
            "userName": "updated-user",
            "name": {"givenName": "Updated", "familyName": "User"},
            "emails": [{"value": "updated@example.com", "type": "work"}],
            "active": True,
        },
    )

    SCIMService._apply_patch(identity, operation)

    assert identity.user_name == "updated-user"
    assert identity.user.name == "Updated User"
    assert identity.user.email == "updated@example.com"
    assert identity.is_active is True


def test_apply_patch_remove_email_clears_user_email():
    identity = _identity()
    operation = SCIMUserPatchOperation(op="remove", path="emails")

    SCIMService._apply_patch(identity, operation)

    assert identity.user.email is None


def test_external_identity_cleanup_targets_scim_memberships_links_and_manager_references():
    repository = SCIMUserRepository()
    identity = _identity()
    db = MagicMock()

    repository.delete_external_data(db, identity)

    statements = [
        str(call.args[0].compile(dialect=postgresql.dialect()))
        for call in db.execute.call_args_list
    ]
    assert any("DELETE FROM external_group_membership" in statement for statement in statements)
    assert any("DELETE FROM oidc_identity_link" in statement for statement in statements)
    assert any("UPDATE user_external_identity" in statement for statement in statements)
    db.delete.assert_called_once_with(identity)


def test_remove_members_without_value_clears_all_group_memberships():
    service = SCIMService()
    group = SimpleNamespace(
        memberships=[
            SimpleNamespace(user_external_identity_id=1),
            SimpleNamespace(user_external_identity_id=2),
        ]
    )

    service._patch_group_attribute(None, None, group, "remove", "members", None)

    assert group.memberships == []


def test_replace_filtered_member_preserves_other_group_members(monkeypatch):
    service = SCIMService()
    group = SimpleNamespace(
        memberships=[
            SimpleNamespace(
                user_external_identity_id=1,
                user_external_identity=SimpleNamespace(id=1, scim_id="scim-user-1"),
            ),
            SimpleNamespace(
                user_external_identity_id=2,
                user_external_identity=SimpleNamespace(id=2, scim_id="scim-user-2"),
            ),
        ]
    )
    monkeypatch.setattr(
        service,
        "_resolve_members",
        lambda _db, _connection, _members: [
            SimpleNamespace(id=1, scim_id="scim-user-1")
        ],
    )

    service._patch_group_attribute(
        None,
        None,
        group,
        "replace",
        'members[value eq "scim-user-1"]',
        {"value": "scim-user-1", "type": "User"},
    )

    assert sorted(member.user_external_identity_id for member in group.memberships) == [1, 2]


def test_add_group_member_preserves_existing_membership(monkeypatch):
    service = SCIMService()
    existing_identity = SimpleNamespace(id=1, scim_id="scim-user-1")
    added_identity = SimpleNamespace(id=2, scim_id="scim-user-2")
    group = SimpleNamespace(
        memberships=[
            SimpleNamespace(
                user_external_identity_id=existing_identity.id,
                user_external_identity=existing_identity,
            )
        ]
    )
    monkeypatch.setattr(
        service, "_resolve_members", lambda _db, _connection, _members: [added_identity]
    )

    service._patch_group_attribute(
        None, None, group, "add", "members", {"value": "scim-user-2", "type": "User"}
    )

    assert sorted(member.user_external_identity_id for member in group.memberships) == [1, 2]
