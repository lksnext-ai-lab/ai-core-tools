from datetime import UTC, datetime

from models.user_avatar import UserAvatar
from sqlalchemy import delete, select
from sqlalchemy.orm import Session


class UserAvatarRepository:

    def __init__(self, db: Session):
        self.db = db

    def get(self, user_id: int) -> UserAvatar | None:
        return self.db.get(UserAvatar, user_id)

    def get_updated_at(self, user_id: int) -> datetime | None:
        """The avatar's version without loading its bytes."""
        return self.db.execute(
            select(UserAvatar.updated_at).where(UserAvatar.user_id == user_id)
        ).scalar_one_or_none()

    def upsert(self, user_id: int, content: bytes, content_type: str) -> UserAvatar:
        avatar = self.get(user_id)
        if avatar is None:
            avatar = UserAvatar(user_id=user_id)
            self.db.add(avatar)
        avatar.content = content
        avatar.content_type = content_type
        avatar.updated_at = datetime.now(UTC)
        self.db.flush()
        return avatar

    def delete(self, user_id: int) -> bool:
        result = self.db.execute(delete(UserAvatar).where(UserAvatar.user_id == user_id))
        return result.rowcount > 0
