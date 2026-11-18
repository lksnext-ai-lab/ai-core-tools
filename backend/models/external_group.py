from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint, text
from sqlalchemy.orm import relationship

from db.database import Base


class ExternalGroup(Base):
    __tablename__ = "external_group"
    __table_args__ = (
        UniqueConstraint("connection_id", "external_id", name="uq_external_group_connection_external_id"),
        UniqueConstraint("connection_id", "scim_id", name="uq_external_group_connection_scim_id"),
        Index("ix_external_group_connection_id", "connection_id"),
        Index(
            "ix_external_group_active",
            "is_active",
            postgresql_where=text("is_active IS TRUE"),
        ),
    )

    id = Column(Integer, primary_key=True)
    connection_id = Column(
        Integer,
        ForeignKey("provisioning_connection.id", ondelete="CASCADE"),
        nullable=False,
    )
    external_id = Column(String(255), nullable=False)
    scim_id = Column(String(255), nullable=False)
    display_name = Column(String(255), nullable=False)
    is_active = Column(Boolean, nullable=False, default=True, server_default="true")
    last_synced_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.now)
    updated_at = Column(DateTime, nullable=False, default=datetime.now, onupdate=datetime.now)

    connection = relationship(
        "ProvisioningConnection",
        back_populates="groups",
        lazy="selectin",
    )
    memberships = relationship(
        "ExternalGroupMembership",
        back_populates="group",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="selectin",
    )
    access_rules = relationship(
        "GroupAppAccessRule",
        back_populates="group",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="selectin",
    )
