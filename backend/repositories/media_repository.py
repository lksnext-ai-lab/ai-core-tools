from typing import List, Optional
from utils import logger
from models.media import Media
from sqlalchemy.orm import Session

class MediaRepository:
    @staticmethod
    def create(media: Media, db: Session) -> Media:
        db.add(media)
        db.flush()
        return media
    
    @staticmethod
    def get_by_id(media_id: int, db: Session) -> Optional[Media]:
        return db.query(Media).filter(Media.media_id == media_id).first()
    
    @staticmethod
    def get_by_repository_id(repository_id: int, db: Session) -> List[Media]:
        return db.query(Media).filter(Media.repository_id == repository_id).all()

    @staticmethod
    def update_status(media_id: int, status: str, db: Session):
        """Update media status"""
        media = db.query(Media).filter(Media.media_id == media_id).first()
        if media:
            media.status = status
            db.commit()
            logger.info(f"Updated media {media_id} status to: {status}")
    
    @staticmethod
    def delete(media: Media, db: Session):
        db.delete(media)
        db.commit()