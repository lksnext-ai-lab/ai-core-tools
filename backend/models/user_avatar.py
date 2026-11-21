from db.database import Base
from sqlalchemy import Column, ForeignKey, Integer

from models.stored_image import StoredImageMixin


class UserAvatar(StoredImageMixin, Base):
    """A user's profile picture, deleted with the user (FK CASCADE)."""
    __tablename__ = 'user_avatar'
    owner_column = 'user_id'

    user_id = Column(Integer, ForeignKey('User.user_id', ondelete='CASCADE'), primary_key=True)
