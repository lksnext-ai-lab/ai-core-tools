from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, UniqueConstraint
from sqlalchemy.orm import relationship

from db.database import Base


class ExternalGroupMembership(Base):
    __tablename__ = "external_group_membership"
    __table_args__ = (
        UniqueConstraint("group_id", "user_external_identity_id", name="uq_external_group_membership_group_identity"),
        Index("ix_external_group_membership_group_id", "group_id"),
        Index("ix_external_group_membership_user_external_identity_id", "user_external_identity_id"),
    )

    id = Column(Integer, primary_key=True)
    group_id = Column(Integer, ForeignKey("external_group.id", ondelete="CASCADE"), nullable=False)
    user_external_identity_id = Column(
        Integer,
        ForeignKey("user_external_identity.id", ondelete="CASCADE"),
        nullable=False,
    )
    created_at = Column(DateTime, nullable=False, default=datetime.now)
    updated_at = Column(DateTime, nullable=False, default=datetime.now, onupdate=datetime.now)

    group = relationship(
        "ExternalGroup",
        back_populates="memberships",
        lazy="selectin",
    )
    user_external_identity = relationship("UserExternalIdentity", lazy="selectin")
