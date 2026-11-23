from db.database import Base
from sqlalchemy import Column, ForeignKey, Integer

from models.stored_image import StoredImageMixin


class AppImage(StoredImageMixin, Base):
    """An App's image (shown in the Apps list and settings), deleted with the App (FK CASCADE)."""
    __tablename__ = 'app_image'
    owner_column = 'app_id'

    app_id = Column(Integer, ForeignKey('App.app_id', ondelete='CASCADE'), primary_key=True)
