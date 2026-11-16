from typing import Optional

from sqlalchemy.orm import Session

from models.provisioning_connection import ProvisioningConnection


class ProvisioningConnectionRepository:
    """Repository for connection-scoped SCIM authentication lookups."""

    @staticmethod
    def get_by_key(db: Session, connection_key: str) -> Optional[ProvisioningConnection]:
        """Return the connection identified by its opaque URL key."""
        return (
            db.query(ProvisioningConnection)
            .filter(ProvisioningConnection.connection_key == connection_key)
            .first()
        )

    @staticmethod
    def get_active_static_bearer_connections(db: Session) -> list[ProvisioningConnection]:
        """Return active connections eligible for static bearer authentication."""
        return (
            db.query(ProvisioningConnection)
            .filter(
                ProvisioningConnection.is_active.is_(True),
                ProvisioningConnection.auth_mode == "static_bearer",
            )
            .all()
        )
