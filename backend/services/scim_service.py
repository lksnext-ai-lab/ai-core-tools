import asyncio
import uuid
from datetime import datetime
import re
from typing import Any, Optional

import bcrypt
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from models.user import User
from models.user_external_identity import UserExternalIdentity
from models.external_group import ExternalGroup
from models.external_group_membership import ExternalGroupMembership
from models.provisioning_connection import ProvisioningConnection
from repositories.provisioning_connection_repository import ProvisioningConnectionRepository
from repositories.scim_user_repository import SCIMUserRepository
from repositories.scim_group_repository import SCIMGroupRepository
from schemas.scim_schemas import (
    SCIMEmail,
    SCIMName,
    SCIMUserCreate,
    SCIMUserPatch,
    SCIMUserPatchOperation,
    SCIMUserResponse,
    SCIMGroupCreate,
    SCIMGroupMember,
    SCIMGroupPatch,
    SCIMGroupResponse,
)
from utils.logger import get_logger

logger = get_logger(__name__)


class SCIMAuthenticationError(Exception):
    """Authentication failure with an HTTP status and SCIM-safe detail."""

    def __init__(self, status_code: int, detail: str, authenticate: bool = False) -> None:
        self.status_code = status_code
        self.detail = detail
        self.authenticate = authenticate
        super().__init__(detail)


class SCIMRequestError(Exception):
    """A SCIM protocol error produced by a resource service."""

    def __init__(self, status_code: int, detail: str) -> None:
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


class SCIMService:
    """Business logic for provider-neutral SCIM discovery."""

    def __init__(
        self,
        connection_repository: Optional[ProvisioningConnectionRepository] = None,
    ) -> None:
        self.connection_repository = connection_repository or ProvisioningConnectionRepository()
        self.user_repository = SCIMUserRepository()
        self.group_repository = SCIMGroupRepository()

    @staticmethod
    def _email(payload_emails: list[SCIMEmail]) -> Optional[str]:
        """Return the work email, falling back to the primary email."""
        for email in payload_emails:
            if (email.type or "").lower() == "work":
                return email.value
        for email in payload_emails:
            if email.primary:
                return email.value
        return payload_emails[0].value if payload_emails else None

    @staticmethod
    def _display_name(payload: SCIMUserCreate, current: Optional[str] = None) -> Optional[str]:
        """Map the supported SCIM name fields to the local display name."""
        if payload.displayName is not None:
            return payload.displayName
        if payload.name:
            if payload.name.formatted:
                return payload.name.formatted
            value = " ".join(
                item for item in (payload.name.givenName, payload.name.familyName) if item
            )
            if value:
                return value
        return current

    @staticmethod
    def _response(identity: UserExternalIdentity) -> SCIMUserResponse:
        """Convert a provisioned identity to a typed SCIM resource."""
        email = identity.user.email
        return SCIMUserResponse(
            id=identity.scim_id,
            externalId=identity.external_id,
            userName=identity.user_name,
            active=identity.is_active,
            displayName=identity.user.name,
            name=SCIMName(formatted=identity.user.name) if identity.user.name else None,
            emails=[SCIMEmail(value=email, type="work", primary=True)] if email else [],
            meta={
                "resourceType": "User",
                "location": f"/scim/v2/{identity.connection.connection_key}/Users/{identity.scim_id}",
                "created": identity.created_at.isoformat(),
                "lastModified": identity.updated_at.isoformat(),
            },
        )

    def list_users(
        self,
        db: Session,
        connection: ProvisioningConnection,
        start_index: int,
        count: int,
        filter_expression: Optional[str],
    ) -> tuple[list[SCIMUserResponse], int]:
        """List users using the supported SCIM equality filters."""
        if start_index < 1 or count < 0:
            raise SCIMRequestError(400, "startIndex must be at least 1 and count cannot be negative.")
        external_id = user_name = None
        if filter_expression:
            parts = filter_expression.split(" ", 2)
            if len(parts) != 3 or parts[1].lower() != "eq":
                raise SCIMRequestError(400, "Only equality filters for externalId and userName are supported.")
            value = parts[2].strip().strip('"')
            if parts[0] == "externalId":
                external_id = value
            elif parts[0] == "userName":
                user_name = value
            else:
                raise SCIMRequestError(400, "Only externalId and userName filters are supported.")
        rows, total = self.user_repository.find(
            db, connection.id, start_index, min(count, 1000), external_id, user_name
        )
        return [self._response(row) for row in rows], total

    def get_user(
        self, db: Session, connection: ProvisioningConnection, scim_id: str
    ) -> SCIMUserResponse:
        """Retrieve one user within the authenticated connection."""
        identity = self.user_repository.get_by_scim_id(db, connection.id, scim_id)
        if identity is None:
            raise SCIMRequestError(404, "User not found.")
        return self._response(identity)

    def upsert_user(
        self, db: Session, connection: ProvisioningConnection, payload: SCIMUserCreate
    ) -> tuple[SCIMUserResponse, bool]:
        """Create or idempotently reconcile a connection-scoped SCIM user."""
        identity = self.user_repository.get_by_external_id(
            db, connection.id, payload.externalId
        )
        if identity is not None and not payload.active:
            response = self._deprovision_user(db, identity)
            return response, False

        email = self._email(payload.emails)
        mapped_user = self.user_repository.get_oidc_linked_user(
            db, connection.id, payload.externalId
        )
        existing_user = self._resolve_upsert_users(
            db, connection, payload, identity, email, mapped_user
        )
        created = identity is None
        try:
            if identity is None:
                identity = self._create_external_identity(
                    db, connection, payload, email, mapped_user, existing_user
                )
            else:
                self._update_external_identity(identity, payload, email)
            identity.last_synced_at = datetime.now()
            db.commit()
            db.refresh(identity)
            return self._response(identity), created
        except IntegrityError:
            db.rollback()
            raise SCIMRequestError(409, "The SCIM user conflicts with an existing identity.")

    def _resolve_upsert_users(
        self,
        db: Session,
        connection: ProvisioningConnection,
        payload: SCIMUserCreate,
        identity: Optional[UserExternalIdentity],
        email: Optional[str],
        mapped_user: Optional[User],
    ) -> Optional[User]:
        if (
            identity is not None
            and mapped_user is not None
            and identity.user_id != mapped_user.user_id
        ):
            raise SCIMRequestError(409, "The external ID is mapped to conflicting Mattin users.")

        existing_user = self._find_email_user(db, email, identity, mapped_user)
        if identity is None:
            self._validate_unlinked_user(db, mapped_user, existing_user)
        return existing_user

    def _find_email_user(
        self,
        db: Session,
        email: Optional[str],
        identity: Optional[UserExternalIdentity],
        mapped_user: Optional[User],
    ) -> Optional[User]:
        if not email:
            return None
        email_users = self.user_repository.get_email_users(db, email)
        if len(email_users) > 1:
            raise SCIMRequestError(409, "The email matches multiple Mattin users.")
        existing_user = email_users[0] if email_users else None
        allowed_user_id = None
        if identity is not None:
            allowed_user_id = identity.user_id
        elif mapped_user is not None:
            allowed_user_id = mapped_user.user_id
        if (
            existing_user is not None
            and allowed_user_id is not None
            and existing_user.user_id != allowed_user_id
        ):
            raise SCIMRequestError(409, "The email is already assigned to another Mattin user.")
        return existing_user

    def _validate_unlinked_user(
        self,
        db: Session,
        mapped_user: Optional[User],
        existing_user: Optional[User],
    ) -> None:
        candidate_user = mapped_user or existing_user
        if candidate_user is None:
            return
        linked_identities = self.user_repository.get_external_identities_for_user(
            db, candidate_user.user_id
        )
        if not linked_identities:
            return
        if mapped_user is not None:
            raise SCIMRequestError(
                409,
                "The external ID is mapped to a Mattin user already linked to another identity.",
            )
        raise SCIMRequestError(
            409,
            "The email belongs to a Mattin user already linked to another external identity.",
        )

    def _create_external_identity(
        self,
        db: Session,
        connection: ProvisioningConnection,
        payload: SCIMUserCreate,
        email: Optional[str],
        mapped_user: Optional[User],
        existing_user: Optional[User],
    ) -> UserExternalIdentity:
        user = mapped_user or existing_user
        if user is None:
            user = User(
                email=email,
                name=self._display_name(payload),
                is_active=payload.active,
                auth_method="scim",
            )
            db.add(user)
            db.flush()
        else:
            # Explicit OIDC mappings and the safe email bootstrap both select
            # the local account; never overwrite a conflicting local email.
            if (
                mapped_user is not None
                and email
                and user.email
                and user.email.lower() == email.lower()
            ):
                user.email = email
            user.name = self._display_name(payload, user.name)
            user.is_active = payload.active

        identity = UserExternalIdentity(
            user_id=user.user_id,
            connection_id=connection.id,
            external_id=payload.externalId,
            scim_id=str(uuid.uuid4()),
            user_name=payload.userName,
            is_active=payload.active,
            last_synced_at=datetime.now(),
        )
        db.add(identity)
        return identity

    def _update_external_identity(
        self,
        identity: UserExternalIdentity,
        payload: SCIMUserCreate,
        email: Optional[str],
    ) -> None:
        identity.user_name = payload.userName
        identity.is_active = payload.active
        identity.user.is_active = payload.active
        identity.user.name = self._display_name(payload, identity.user.name)
        if email is not None:
            identity.user.email = email

    def patch_user(
        self,
        db: Session,
        connection: ProvisioningConnection,
        scim_id: str,
        patch: SCIMUserPatch,
    ) -> SCIMUserResponse:
        """Apply supported SCIM PATCH operations atomically."""
        identity = self.user_repository.get_by_scim_id(db, connection.id, scim_id)
        if identity is None:
            raise SCIMRequestError(404, "User not found.")
        original_name = identity.user.name
        original_email = identity.user.email
        for operation in patch.Operations:
            op = operation.op.lower()
            if op not in {"add", "replace", "remove"}:
                raise SCIMRequestError(400, f"Unsupported PATCH operation: {operation.op}.")
            self._apply_patch(identity, operation)
        if not identity.is_active:
            identity.user.name = original_name
            identity.user.email = original_email
            return self._deprovision_user(db, identity)

        identity.user.is_active = identity.is_active
        identity.last_synced_at = datetime.now()
        try:
            db.commit()
            db.refresh(identity)
            return self._response(identity)
        except IntegrityError:
            db.rollback()
            raise SCIMRequestError(409, "The updated email is already assigned to another Mattin user.")

    def delete_user(
        self, db: Session, connection: ProvisioningConnection, scim_id: str
    ) -> None:
        """Deprovision a user while retaining its local account and history."""
        identity = self.user_repository.get_by_scim_id(db, connection.id, scim_id)
        if identity is None:
            raise SCIMRequestError(404, "User not found.")
        self._deprovision_user(db, identity)

    def _deprovision_user(
        self, db: Session, identity: UserExternalIdentity
    ) -> SCIMUserResponse:
        """Deactivate the Mattin account and remove its external identity data."""
        identity.is_active = False
        identity.user.is_active = False
        response = self._response(identity)
        self.user_repository.delete_external_data(db, identity)
        db.commit()
        return response

    @staticmethod
    def _group_response(group: ExternalGroup) -> SCIMGroupResponse:
        """Convert an external group and its direct memberships to SCIM."""
        members = [
            SCIMGroupMember(
                value=membership.user_external_identity.scim_id,
                display=membership.user_external_identity.user.name,
                type="User",
                ref=(
                    f"/scim/v2/{group.connection.connection_key}/Users/"
                    f"{membership.user_external_identity.scim_id}"
                ),
            )
            for membership in group.memberships
        ]
        return SCIMGroupResponse(
            id=group.scim_id,
            externalId=group.external_id,
            displayName=group.display_name,
            members=members,
            meta={
                "resourceType": "Group",
                "location": f"/scim/v2/{group.connection.connection_key}/Groups/{group.scim_id}",
                "created": group.created_at.isoformat(),
                "lastModified": group.updated_at.isoformat(),
            },
        )

    @staticmethod
    def _group_filter(filter_expression: Optional[str]) -> tuple[Optional[str], Optional[str]]:
        """Parse the equality filters supported for Groups."""
        if not filter_expression:
            return None, None
        parts = filter_expression.split(" ", 2)
        if len(parts) != 3 or parts[1].lower() != "eq":
            raise SCIMRequestError(400, "Only equality filters for externalId and displayName are supported.")
        value = parts[2].strip().strip('"')
        if parts[0] == "externalId":
            return value, None
        if parts[0] == "displayName":
            return None, value
        raise SCIMRequestError(400, "Only externalId and displayName filters are supported.")

    def list_groups(
        self, db: Session, connection: ProvisioningConnection, start_index: int,
        count: int, filter_expression: Optional[str],
    ) -> tuple[list[SCIMGroupResponse], int]:
        """List active Groups using supported SCIM equality filters."""
        if start_index < 1 or count < 0:
            raise SCIMRequestError(400, "startIndex must be at least 1 and count cannot be negative.")
        external_id, display_name = self._group_filter(filter_expression)
        rows, total = self.group_repository.find(
            db, connection.id, start_index, min(count, 1000), external_id, display_name
        )
        return [self._group_response(row) for row in rows], total

    def get_group(
        self, db: Session, connection: ProvisioningConnection, scim_id: str
    ) -> SCIMGroupResponse:
        """Retrieve one active Group within the authenticated connection."""
        group = self.group_repository.get_by_scim_id(db, connection.id, scim_id)
        if group is None:
            raise SCIMRequestError(404, "Group not found.")
        return self._group_response(group)

    def _resolve_members(
        self, db: Session, connection: ProvisioningConnection, members: list[SCIMGroupMember]
    ) -> list[UserExternalIdentity]:
        """Resolve SCIM member values to Users in exactly this connection."""
        identities: list[UserExternalIdentity] = []
        seen: set[str] = set()
        for member in members:
            if member.type.lower() != "user":
                raise SCIMRequestError(400, "Only User Group members are supported.")
            if member.value in seen:
                continue
            seen.add(member.value)
            identity = self.user_repository.get_by_scim_id(db, connection.id, member.value)
            if identity is None or not identity.is_active:
                raise SCIMRequestError(
                    409, f"Group member '{member.value}' is unknown or belongs to another connection."
                )
            identities.append(identity)
        return identities

    @staticmethod
    def _set_group_members(
        db: Session, group: ExternalGroup, identities: list[UserExternalIdentity]
    ) -> None:
        """Replace direct memberships while retaining local users."""
        wanted = {identity.id for identity in identities}
        group.memberships[:] = [
            membership for membership in group.memberships
            if membership.user_external_identity_id in wanted
        ]
        present = {membership.user_external_identity_id for membership in group.memberships}
        for identity in identities:
            if identity.id not in present:
                group.memberships.append(
                    ExternalGroupMembership(user_external_identity_id=identity.id)
                )

    def upsert_group(
        self, db: Session, connection: ProvisioningConnection, payload: SCIMGroupCreate
    ) -> tuple[SCIMGroupResponse, bool]:
        """Create or idempotently reconcile a connection-scoped Group."""
        group = self.group_repository.get_by_external_id(db, connection.id, payload.externalId)
        identities = self._resolve_members(db, connection, payload.members)
        created = group is None
        if group is None:
            group = ExternalGroup(
                connection_id=connection.id, external_id=payload.externalId,
                scim_id=str(uuid.uuid4()), display_name=payload.displayName,
            )
            db.add(group)
            db.flush()
        else:
            group.display_name = payload.displayName
            group.is_active = True
        group.last_synced_at = datetime.now()
        self._set_group_members(db, group, identities)
        try:
            db.commit()
            db.refresh(group)
            return self.get_group(db, connection, group.scim_id), created
        except IntegrityError:
            db.rollback()
            raise SCIMRequestError(409, "The SCIM group conflicts with an existing identity.")

    def patch_group(
        self, db: Session, connection: ProvisioningConnection, scim_id: str, patch: SCIMGroupPatch
    ) -> SCIMGroupResponse:
        """Apply supported displayName and direct-membership PATCH operations."""
        group = self.group_repository.get_by_scim_id(db, connection.id, scim_id)
        if group is None:
            raise SCIMRequestError(404, "Group not found.")
        for operation in patch.Operations:
            op = operation.op.lower()
            path = (operation.path or "").strip().lower()
            if op not in {"add", "replace", "remove"}:
                raise SCIMRequestError(400, f"Unsupported PATCH operation: {operation.op}.")
            if not path and isinstance(operation.value, dict):
                for key, value in operation.value.items():
                    self._patch_group_attribute(db, connection, group, op, key, value)
            else:
                self._patch_group_attribute(db, connection, group, op, path, operation.value)
        group.last_synced_at = datetime.now()
        try:
            db.commit()
            return self.get_group(db, connection, scim_id)
        except IntegrityError:
            db.rollback()
            raise SCIMRequestError(409, "The updated Group conflicts with an existing membership.")

    def _patch_group_attribute(
        self, db: Session, connection: ProvisioningConnection, group: ExternalGroup,
        operation: str, path: str, value: object,
    ) -> None:
        """Apply one supported Group PATCH attribute."""
        if path == "displayname":
            if operation == "remove":
                raise SCIMRequestError(400, "displayName cannot be removed.")
            group.display_name = str(value)
            return
        if path.startswith("members[") and self._patch_filtered_group_member(
                db, connection, group, operation, path, value
            ):
                return
        if path == "members" or path.startswith("members["):
            self._patch_group_members(db, connection, group, operation, value)
            return
        raise SCIMRequestError(400, f"Unsupported PATCH path: {path}.")

    def _patch_filtered_group_member(
        self,
        db: Session,
        connection: ProvisioningConnection,
        group: ExternalGroup,
        operation: str,
        path: str,
        value: object,
    ) -> bool:
        match = re.search(r'value\s+eq\s+"([^"]+)"', path, re.IGNORECASE)
        if not match:
            raise SCIMRequestError(400, "Unsupported members PATCH path.")
        target_scim_id = match.group(1)
        if operation == "remove":
            group.memberships[:] = [
                item for item in group.memberships
                if item.user_external_identity.scim_id != target_scim_id
            ]
            return True
        if operation == "replace":
            resolved = self._resolve_members(
                db,
                connection,
                [
                    SCIMGroupMember.model_validate(item)
                    for item in self._member_values(value)
                ],
            )
            current = [
                item.user_external_identity
                for item in group.memberships
                if item.user_external_identity.scim_id != target_scim_id
            ]
            self._set_group_members(db, group, current + resolved)
            return True
        return False

    def _patch_group_members(
        self,
        db: Session,
        connection: ProvisioningConnection,
        group: ExternalGroup,
        operation: str,
        value: object,
    ) -> None:
        if operation == "remove" and value is None:
            group.memberships.clear()
            return
        resolved = self._resolve_members(
            db,
            connection,
            [
                SCIMGroupMember.model_validate(item)
                for item in self._member_values(value)
            ],
        )
        if operation == "replace":
            self._set_group_members(db, group, resolved)
        elif operation == "remove":
            remove_ids = {identity.id for identity in resolved}
            group.memberships[:] = [
                item for item in group.memberships
                if item.user_external_identity_id not in remove_ids
            ]
        else:
            current = [item.user_external_identity for item in group.memberships]
            self._set_group_members(db, group, current + resolved)

    @staticmethod
    def _member_values(value: object) -> list[object]:
        if isinstance(value, list):
            return value
        if value is None:
            return []
        return [value]

    def delete_group(
        self, db: Session, connection: ProvisioningConnection, scim_id: str
    ) -> None:
        """Deactivate a Group and remove memberships without deleting local users."""
        group = self.group_repository.get_by_scim_id(db, connection.id, scim_id)
        if group is None:
            raise SCIMRequestError(404, "Group not found.")
        group.is_active = False
        group.memberships.clear()
        group.last_synced_at = datetime.now()
        db.commit()

    @staticmethod
    def _apply_patch(identity: UserExternalIdentity, operation: SCIMUserPatchOperation) -> None:
        """Apply one validated supported PATCH attribute."""
        path = SCIMService._normalize_patch_path(operation.path)
        value = operation.value
        if not path and isinstance(value, dict):
            SCIMService._apply_patch_object(identity, operation, value)
            return
        if path == "active":
            identity.is_active = (
                value if isinstance(value, bool) else str(value).lower() == "true"
            )
        elif path == "externalid":
            SCIMService._validate_external_id_patch(identity, operation, value)
        elif path == "username":
            identity.user_name = str(value)
        elif path in {"displayname", "name.formatted"}:
            identity.user.name = str(value) if value is not None else None
        elif path.startswith("emails"):
            SCIMService._apply_email_patch(identity, operation, value)
        elif path in {"", "name"} and isinstance(value, dict):
            SCIMService._apply_name_patch(identity, value)
        else:
            raise SCIMRequestError(400, f"Unsupported PATCH path: {operation.path}.")

    @staticmethod
    def _normalize_patch_path(path: Optional[str]) -> str:
        normalized_path = (path or "").strip().lower()
        if ":" in normalized_path:
            normalized_path = normalized_path.rsplit(":", 1)[-1]
        return normalized_path

    @staticmethod
    def _apply_patch_object(
        identity: UserExternalIdentity,
        operation: SCIMUserPatchOperation,
        values: dict[str, Any],
    ) -> None:
        for key, value in values.items():
            SCIMService._apply_patch(
                identity,
                SCIMUserPatchOperation(op=operation.op, path=key, value=value),
            )

    @staticmethod
    def _validate_external_id_patch(
        identity: UserExternalIdentity,
        operation: SCIMUserPatchOperation,
        value: object,
    ) -> None:
        if operation.op.lower() == "remove" or str(value) != identity.external_id:
            raise SCIMRequestError(409, "externalId cannot be changed.")

    @staticmethod
    def _apply_email_patch(
        identity: UserExternalIdentity,
        operation: SCIMUserPatchOperation,
        value: object,
    ) -> None:
        if isinstance(value, list):
            email = SCIMService._email(
                [SCIMEmail.model_validate(item) for item in value]
            )
        elif isinstance(value, dict):
            email = value.get("value")
        else:
            email = value
        if email:
            identity.user.email = str(email)
        elif operation.op.lower() == "remove":
            identity.user.email = None

    @staticmethod
    def _apply_name_patch(
        identity: UserExternalIdentity, value: dict[str, Any]
    ) -> None:
        identity.user.name = " ".join(
            str(item) for item in (value.get("givenName"), value.get("familyName")) if item
        ) or value.get("formatted")

    async def authenticate(
        self,
        db: Session,
        connection_key: str,
        authorization: Optional[str],
    ) -> ProvisioningConnection:
        """Authenticate a static bearer token for exactly one connection."""
        if not authorization:
            raise SCIMAuthenticationError(401, "A bearer token is required.", authenticate=True)

        scheme, _, token = authorization.partition(" ")
        if scheme.lower() != "bearer" or not token.strip():
            raise SCIMAuthenticationError(401, "A bearer token is required.", authenticate=True)
        token = token.strip()

        connection = self.connection_repository.get_by_key(db, connection_key)
        if connection is None:
            raise SCIMAuthenticationError(401, "Invalid SCIM credentials.", authenticate=True)
        if not connection.is_active:
            raise SCIMAuthenticationError(403, "The SCIM connection is inactive.")
        if connection.auth_mode != "static_bearer":
            raise SCIMAuthenticationError(403, "The SCIM connection authentication mode is unsupported.")

        if await self._verify(token, connection.credential_hash):
            return connection

        # A valid token belonging to another connection must not be usable at
        # this URL.  The token itself is never logged or persisted here.
        for candidate in self.connection_repository.get_active_static_bearer_connections(db):
            if candidate.id != connection.id and await self._verify(token, candidate.credential_hash):
                raise SCIMAuthenticationError(403, "The bearer token is not valid for this connection.")

        raise SCIMAuthenticationError(401, "Invalid SCIM credentials.", authenticate=True)

    @staticmethod
    async def _verify(token: str, credential_hash: str) -> bool:
        """Verify bcrypt off the event loop."""
        try:
            return await asyncio.to_thread(
                bcrypt.checkpw,
                token.encode("utf-8"),
                credential_hash.encode("utf-8"),
            )
        except (ValueError, TypeError):
            return False


scim_service = SCIMService()
