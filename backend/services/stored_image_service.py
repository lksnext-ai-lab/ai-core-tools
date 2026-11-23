"""Pictures stored per owner: user avatars and App images (one service, parametrised by the table)."""
from collections.abc import Iterable
from datetime import datetime

from models.app_image import AppImage
from models.stored_image import StoredImageMixin
from models.user_avatar import UserAvatar
from repositories.stored_image_repository import StoredImageRepository
from sqlalchemy.orm import Session
from utils.image_normalization import IMAGE_CONTENT_TYPE


class StoredImageService:

    def __init__(self, db: Session, model: type[StoredImageMixin]):
        self.db = db
        self.repository = StoredImageRepository(db, model)

    @classmethod
    def user_avatars(cls, db: Session) -> "StoredImageService":
        return cls(db, UserAvatar)

    @classmethod
    def app_images(cls, db: Session) -> "StoredImageService":
        return cls(db, AppImage)

    def get(self, owner_id: int) -> StoredImageMixin | None:
        return self.repository.get(owner_id)

    def get_updated_at(self, owner_id: int) -> datetime | None:
        return self.repository.get_updated_at(owner_id)

    def get_versions(self, owner_ids: Iterable[int]) -> dict[int, datetime]:
        return self.repository.get_versions(owner_ids)

    def save(self, owner_id: int, normalized_image: bytes) -> StoredImageMixin:
        """Store an image already produced by ``normalize_square_image``."""
        image = self.repository.upsert(owner_id, normalized_image, IMAGE_CONTENT_TYPE)
        self.db.commit()
        return image

    def delete(self, owner_id: int) -> bool:
        deleted = self.repository.delete(owner_id)
        self.db.commit()
        return deleted
