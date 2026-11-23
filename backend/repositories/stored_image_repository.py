from collections.abc import Iterable
from datetime import UTC, datetime

from models.stored_image import StoredImageMixin
from sqlalchemy import delete, select
from sqlalchemy.orm import Session


class StoredImageRepository:
    """Data access for any ``StoredImageMixin`` table (``UserAvatar``, ``AppImage``)."""

    def __init__(self, db: Session, model: type[StoredImageMixin]):
        self.db = db
        self.model = model
        self.owner_id = getattr(model, model.owner_column)

    def get(self, owner_id: int) -> StoredImageMixin | None:
        return self.db.get(self.model, owner_id)

    def get_updated_at(self, owner_id: int) -> datetime | None:
        """The image's version without loading its bytes."""
        return self.db.execute(
            select(self.model.updated_at).where(self.owner_id == owner_id)
        ).scalar_one_or_none()

    def get_versions(self, owner_ids: Iterable[int]) -> dict[int, datetime]:
        """``{owner_id: updated_at}`` for the owners that have an image, in one query."""
        ids = list(owner_ids)
        if not ids:
            return {}
        rows = self.db.execute(select(self.owner_id, self.model.updated_at).where(self.owner_id.in_(ids)))
        return dict(rows.tuples().all())

    def upsert(self, owner_id: int, content: bytes, content_type: str) -> StoredImageMixin:
        image = self.get(owner_id)
        if image is None:
            image = self.model(**{self.model.owner_column: owner_id})
            self.db.add(image)
        image.content = content
        image.content_type = content_type
        image.updated_at = datetime.now(UTC)
        self.db.flush()
        return image

    def delete(self, owner_id: int) -> bool:
        result = self.db.execute(delete(self.model).where(self.owner_id == owner_id))
        return result.rowcount > 0
