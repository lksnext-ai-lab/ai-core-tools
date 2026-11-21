from datetime import UTC, datetime

from db.database import Base
from sqlalchemy import Column, DateTime, ForeignKey, Integer, LargeBinary, String


class UserAvatar(Base):
    """A user's profile picture: one normalised image per user, deleted with the user (FK CASCADE).

    Kept out of "User" so the image bytes are never loaded with the user row.
    """
    __tablename__ = 'user_avatar'

    user_id = Column(Integer, ForeignKey('User.user_id', ondelete='CASCADE'), primary_key=True)
    content = Column(LargeBinary, nullable=False)
    content_type = Column(String(50), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC))
