from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import relationship

from db.database import Base


class OIDCIdentityLink(Base):
    """An administrator-approved mapping between an OIDC subject and SCIM ID."""

    __tablename__ = "oidc_identity_link"
    __table_args__ = (
        UniqueConstraint(
            "issuer",
            "subject",
            name="uq_oidc_identity_link_issuer_subject",
        ),
        UniqueConstraint(
            "connection_id",
            "external_id",
            name="uq_oidc_identity_link_connection_external_id",
        ),
        Index("ix_oidc_identity_link_user_id", "user_id"),
        Index("ix_oidc_identity_link_connection_id", "connection_id"),
    )

    id = Column(Integer, primary_key=True)
    user_id = Column(
        Integer, ForeignKey("User.user_id", ondelete="CASCADE"), nullable=False
    )
    connection_id = Column(
        Integer,
        ForeignKey("provisioning_connection.id", ondelete="CASCADE"),
        nullable=False,
    )
    issuer = Column(String(1024), nullable=False)
    subject = Column(String(512), nullable=False)
    external_id = Column(String(255), nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.now)
    updated_at = Column(DateTime, nullable=False, default=datetime.now, onupdate=datetime.now)

    user = relationship("User", lazy="joined")
    connection = relationship("ProvisioningConnection", lazy="joined")
