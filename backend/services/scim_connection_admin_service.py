import secrets
from typing import Optional

import bcrypt
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from models.provisioning_connection import ProvisioningConnection
from models.oidc_identity_link import OIDCIdentityLink
from models.user import User
from repositories.scim_connection_admin_repository import SCIMConnectionAdminRepository
from schemas.scim_connection_schemas import (
    SCIMConnectionCreate,
    SCIMConnectionCredentialResponse,
    SCIMConnectionDetail,
    SCIMConnectionListItem,
    SCIMConnectionStatusResponse,
    SCIMConnectionUpdate,
    OIDCIdentityLinkCreate,
    OIDCIdentityLinkResponse,
)


class SCIMConnectionNotFoundError(Exception):
    """Raised when an administrative connection target does not exist."""


class SCIMConnectionConflictError(Exception):
    """Raised when a connection violates a uniqueness constraint."""


class SCIMConnectionUpdateConflictError(Exception):
    """Raised when a SCIM connection update is stale or lacks required checks."""


class SCIMIdentityLinkTargetNotFoundError(Exception):
    """Raised when an identity link references a missing local user."""


class SCIMConnectionAdminService:
    """Business logic for administering provider-neutral SCIM connections."""

    def __init__(
        self,
        repository: Optional[SCIMConnectionAdminRepository] = None,
    ) -> None:
        self.repository = repository or SCIMConnectionAdminRepository()

    @staticmethod
    def _new_token() -> str:
        """Generate a bearer token with 512 bits of entropy."""
        return secrets.token_urlsafe(64)

    @staticmethod
    def _new_connection_key() -> str:
        """Generate an opaque URL-safe connection identifier."""
        return secrets.token_urlsafe(32)

    @staticmethod
    def _hash_token(token: str) -> str:
        """Hash a bearer token with bcrypt before persistence."""
        return bcrypt.hashpw(token.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

    @staticmethod
    def _detail(connection: ProvisioningConnection) -> SCIMConnectionDetail:
        """Map an ORM record without exposing its credential hash."""
        return SCIMConnectionDetail.model_validate(connection)

    def list_connections(self, db: Session) -> list[SCIMConnectionListItem]:
        """List connections without credentials."""
        return [
            SCIMConnectionListItem.model_validate(connection)
            for connection in self.repository.list_all(db)
        ]

    def get_connection(self, db: Session, connection_id: int) -> SCIMConnectionDetail:
        """Return one connection without its credential."""
        connection = self.repository.get_by_id(db, connection_id)
        if connection is None:
            raise SCIMConnectionNotFoundError
        return self._detail(connection)

    def update_connection(
        self,
        db: Session,
        connection_id: int,
        payload: SCIMConnectionUpdate,
        keycloak_realm_change_verified: bool = False,
    ) -> SCIMConnectionDetail:
        """Update a connection's display name and external directory identifier."""
        connection = self.repository.get_by_id_for_update(db, connection_id)
        if connection is None:
            raise SCIMConnectionNotFoundError
        if connection.external_directory_id != payload.expected_external_directory_id:
            raise SCIMConnectionUpdateConflictError(
                "The SCIM connection changed during this edit. Reload it and try again."
            )
        if (
            connection.provider_type.lower() == "keycloak"
            and connection.external_directory_id != payload.external_directory_id
            and not keycloak_realm_change_verified
        ):
            raise SCIMConnectionUpdateConflictError(
                "A Keycloak realm change must be checked against its existing targets first."
            )
        connection.display_name = payload.display_name
        connection.external_directory_id = payload.external_directory_id
        try:
            self.repository.save(db, connection)
        except IntegrityError as exc:
            db.rollback()
            raise SCIMConnectionConflictError from exc
        return self._detail(connection)

    def create_connection(
        self, db: Session, payload: SCIMConnectionCreate
    ) -> SCIMConnectionCredentialResponse:
        """Create a connection and return its bearer token exactly once."""
        token = self._new_token()
        connection = ProvisioningConnection(
            provider_type=payload.provider_type,
            external_directory_id=payload.external_directory_id,
            display_name=payload.display_name,
            auth_mode=payload.auth_mode,
            client_id=payload.client_id,
            connection_key=self._new_connection_key(),
            credential_hash=self._hash_token(token),
            is_active=True,
        )
        try:
            self.repository.add(db, connection)
        except IntegrityError as exc:
            db.rollback()
            raise SCIMConnectionConflictError from exc
        return SCIMConnectionCredentialResponse(
            **self._detail(connection).model_dump(),
            bearer_token=token,
        )

    def rotate_token(
        self, db: Session, connection_id: int
    ) -> SCIMConnectionCredentialResponse:
        """Replace a connection token and return the replacement exactly once."""
        connection = self.repository.get_by_id(db, connection_id)
        if connection is None:
            raise SCIMConnectionNotFoundError
        token = self._new_token()
        connection.credential_hash = self._hash_token(token)
        try:
            self.repository.save(db, connection)
        except IntegrityError as exc:
            db.rollback()
            raise SCIMConnectionConflictError from exc
        return SCIMConnectionCredentialResponse(
            **self._detail(connection).model_dump(),
            bearer_token=token,
        )

    def set_active(
        self, db: Session, connection_id: int, is_active: bool
    ) -> SCIMConnectionStatusResponse:
        """Activate or deactivate a connection explicitly."""
        connection = self.repository.get_by_id(db, connection_id)
        if connection is None:
            raise SCIMConnectionNotFoundError
        connection.is_active = is_active
        try:
            self.repository.save(db, connection)
        except IntegrityError as exc:
            db.rollback()
            raise SCIMConnectionConflictError from exc
        return SCIMConnectionStatusResponse.model_validate(connection)

    def create_oidc_identity_link(
        self,
        db: Session,
        connection_id: int,
        payload: OIDCIdentityLinkCreate,
    ) -> OIDCIdentityLinkResponse:
        """Create an explicit, admin-approved OIDC-to-SCIM identity mapping."""
        connection = self.repository.get_by_id(db, connection_id)
        user = db.get(User, payload.user_id)
        if connection is None or user is None:
            raise SCIMIdentityLinkTargetNotFoundError
        link = OIDCIdentityLink(
            user_id=user.user_id,
            connection_id=connection.id,
            issuer=payload.issuer.rstrip("/"),
            subject=payload.subject,
            external_id=payload.external_id,
        )
        try:
            self.repository.add_link(db, link)
        except IntegrityError as exc:
            db.rollback()
            raise SCIMConnectionConflictError from exc
        return OIDCIdentityLinkResponse.model_validate(link)


scim_connection_admin_service = SCIMConnectionAdminService()
