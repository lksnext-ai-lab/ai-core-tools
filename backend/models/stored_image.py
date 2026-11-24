from datetime import UTC, datetime
from typing import ClassVar

from sqlalchemy import Column, DateTime, LargeBinary, String


class StoredImageMixin:
    """One normalised picture per owner row (see ``utils/image_normalization.py``).

    Each concrete table has the owner's id as its primary key (FK ... ON DELETE CASCADE) and names that
    column in ``owner_column``. Kept out of the owner's table so the bytes are never loaded with it.
    """
    owner_column: ClassVar[str]

    content = Column(LargeBinary, nullable=False)
    content_type = Column(String(50), nullable=False)
    # The image's version: clients use it as a cache key.
    updated_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC))
