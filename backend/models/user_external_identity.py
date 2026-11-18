from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint, text
from sqlalchemy.orm import relationship

from db.database import Base


class UserExternalIdentity(Base):
    __tablename__ = "user_external_identity"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("User.user_id", ondelete="CASCADE"), nullable=False)
    connection_id = Column(
        Integer,
        ForeignKey("provisioning_connection.id", ondelete="CASCADE"),
        nullable=False,
    )
    external_id = Column(String(255), nullable=False)
    scim_id = Column(String(255), nullable=False)
    user_name = Column(String(255), nullable=False)
    is_active = Column(Boolean, nullable=False, default=True, server_default="true")
    manager_external_id = Column(String(255), nullable=True)
    manager_identity_id = Column(
        Integer,
        ForeignKey("user_external_identity.id", ondelete="SET NULL"),
        nullable=True,
    )
    department = Column(String(255), nullable=True)
    last_synced_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.now)
    updated_at = Column(DateTime, nullable=False, default=datetime.now, onupdate=datetime.now)

    __table_args__ = (
        UniqueConstraint("user_id", name="uq_user_external_identity_user_id"),
        UniqueConstraint(
            "connection_id",
            "external_id",
            name="uq_user_external_identity_connection_external_id",
        ),
        UniqueConstraint(
            "connection_id",
            "scim_id",
            name="uq_user_external_identity_connection_scim_id",
        ),
        Index("ix_user_external_identity_connection_id", "connection_id"),
        Index("ix_user_external_identity_manager_identity_id", "manager_identity_id"),
        Index(
            "ix_user_external_identity_active",
            "is_active",
            postgresql_where=text("is_active IS TRUE"),
        ),
        {"sqlite_autoincrement": True},
    )

    connection = relationship(
        "ProvisioningConnection",
        back_populates="identities",
        lazy="selectin",
    )
    user = relationship("User", lazy="selectin")
    manager_identity = relationship(
        "UserExternalIdentity",
        remote_side=[id],
        foreign_keys=[manager_identity_id],
        lazy="selectin",
    )
