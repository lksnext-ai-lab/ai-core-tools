from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Index, Integer, String, UniqueConstraint, text
from sqlalchemy.orm import relationship

from db.database import Base


class ProvisioningConnection(Base):
    __tablename__ = "provisioning_connection"
    __table_args__ = (
        UniqueConstraint("provider_type", "external_directory_id", name="uq_provisioning_connection_provider_directory"),
        UniqueConstraint("connection_key", name="uq_provisioning_connection_key"),
        Index(
            "uq_provisioning_connection_client_id",
            "client_id",
            unique=True,
            postgresql_where=text("client_id IS NOT NULL"),
        ),
        Index(
            "ix_provisioning_connection_active",
            "is_active",
            postgresql_where=text("is_active IS TRUE"),
        ),
    )

    id = Column(Integer, primary_key=True)
    provider_type = Column(String(50), nullable=False)
    external_directory_id = Column(String(255), nullable=True)
    connection_key = Column(String(255), nullable=False)
    display_name = Column(String(255), nullable=False)
    auth_mode = Column(String(50), nullable=False)
    client_id = Column(String(255), nullable=True)
    credential_hash = Column(String(255), nullable=False)
    is_active = Column(Boolean, nullable=False, default=True, server_default="true")
    created_at = Column(DateTime, nullable=False, default=datetime.now)
    updated_at = Column(DateTime, nullable=False, default=datetime.now, onupdate=datetime.now)

    identities = relationship(
        "UserExternalIdentity",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="selectin",
    )
    groups = relationship(
        "ExternalGroup",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="selectin",
    )
