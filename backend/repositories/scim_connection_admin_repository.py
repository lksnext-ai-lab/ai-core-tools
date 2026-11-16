from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from models.provisioning_connection import ProvisioningConnection
from models.oidc_identity_link import OIDCIdentityLink


class SCIMConnectionAdminRepository:
    """Repository for bounded administrative SCIM connection operations."""

    @staticmethod
    def list_all(db: Session) -> list[ProvisioningConnection]:
        """Return all connections in stable creation order."""
        statement = select(ProvisioningConnection).order_by(ProvisioningConnection.id)
        return list(db.execute(statement).scalars().all())

    @staticmethod
    def get_by_id(db: Session, connection_id: int) -> Optional[ProvisioningConnection]:
        """Return one connection by its database identifier."""
        statement = select(ProvisioningConnection).where(
            ProvisioningConnection.id == connection_id
        )
        return db.execute(statement).scalar_one_or_none()

    @staticmethod
    def add(db: Session, connection: ProvisioningConnection) -> ProvisioningConnection:
        """Persist a new connection and refresh its generated fields."""
        db.add(connection)
        db.commit()
        db.refresh(connection)
        return connection

    @staticmethod
    def save(db: Session, connection: ProvisioningConnection) -> ProvisioningConnection:
        """Persist changes to an existing connection."""
        db.add(connection)
        db.commit()
        db.refresh(connection)
        return connection

    @staticmethod
    def get_link_by_id(db: Session, link_id: int) -> Optional[OIDCIdentityLink]:
        """Return an identity link by its identifier."""
        statement = select(OIDCIdentityLink).where(OIDCIdentityLink.id == link_id)
        return db.execute(statement).scalar_one_or_none()

    @staticmethod
    def add_link(db: Session, link: OIDCIdentityLink) -> OIDCIdentityLink:
        """Persist an identity link and refresh its timestamps."""
        db.add(link)
        db.commit()
        db.refresh(link)
        return link
