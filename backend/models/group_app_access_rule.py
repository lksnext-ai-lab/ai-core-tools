import enum
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Enum, ForeignKey, Index, Integer, UniqueConstraint, text
from sqlalchemy.orm import relationship

from db.database import Base


class GroupAppAccessRole(str, enum.Enum):
    VIEWER = "viewer"
    EDITOR = "editor"


class GroupAppAccessRule(Base):
    __tablename__ = "group_app_access_rule"
    __table_args__ = (
        UniqueConstraint("group_id", "app_id", name="uq_group_app_access_rule_group_app"),
        Index("ix_group_app_access_rule_group_id", "group_id"),
        Index("ix_group_app_access_rule_app_id", "app_id"),
        Index("ix_group_app_access_rule_created_by_user_id", "created_by_user_id"),
        Index(
            "ix_group_app_access_rule_active",
            "is_active",
            postgresql_where=text("is_active IS TRUE"),
        ),
    )

    id = Column(Integer, primary_key=True)
    group_id = Column(Integer, ForeignKey("external_group.id", ondelete="CASCADE"), nullable=False)
    app_id = Column(Integer, ForeignKey("App.app_id", ondelete="CASCADE"), nullable=False)
    role = Column(Enum(GroupAppAccessRole, name="group_app_access_role"), nullable=False)
    created_by_user_id = Column(
        Integer,
        ForeignKey("User.user_id", ondelete="SET NULL"),
        nullable=True,
    )
    is_active = Column(Boolean, nullable=False, default=True, server_default="true")
    created_at = Column(DateTime, nullable=False, default=datetime.now)
    updated_at = Column(DateTime, nullable=False, default=datetime.now, onupdate=datetime.now)

    group = relationship(
        "ExternalGroup",
        back_populates="access_rules",
        lazy="selectin",
    )
    app = relationship("App", lazy="selectin")
    created_by_user = relationship("User", lazy="selectin")
