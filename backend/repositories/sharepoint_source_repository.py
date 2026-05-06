from typing import List, Optional
from sqlalchemy.orm import Session, joinedload
from models.sharepoint_source import SharePointSource
from models.sharepoint_file import SharePointFile


class SharePointSourceRepository:
    """Repository for SharePointSource data access operations."""

    @staticmethod
    def list_by_app(app_id: int, db: Session) -> List[SharePointSource]:
        """List all SharePoint sources for an app, ordered by creation date descending."""
        return (
            db.query(SharePointSource)
            .filter(SharePointSource.app_id == app_id)
            .order_by(SharePointSource.created_at.desc())
            .all()
        )

    @staticmethod
    def get_by_id(source_id: int, db: Session) -> Optional[SharePointSource]:
        """Fetch a single source by ID, eagerly loading the silo."""
        return (
            db.query(SharePointSource)
            .options(joinedload(SharePointSource.silo))
            .filter(SharePointSource.id == source_id)
            .first()
        )

    @staticmethod
    def get_by_id_and_app(source_id: int, app_id: int, db: Session) -> Optional[SharePointSource]:
        """Fetch a source by ID scoped to an app; returns None if not found."""
        return (
            db.query(SharePointSource)
            .filter(
                SharePointSource.id == source_id,
                SharePointSource.app_id == app_id,
            )
            .first()
        )

    @staticmethod
    def create(source: SharePointSource, db: Session) -> SharePointSource:
        """Persist a new SharePointSource row."""
        db.add(source)
        db.commit()
        db.refresh(source)
        return source

    @staticmethod
    def update(source: SharePointSource, db: Session) -> SharePointSource:
        """Persist changes to an existing SharePointSource row."""
        db.add(source)
        db.commit()
        db.refresh(source)
        return source

    @staticmethod
    def delete(source_id: int, db: Session) -> None:
        """Delete a SharePointSource row (cascades to SharePointFile via FK)."""
        db.query(SharePointSource).filter(SharePointSource.id == source_id).delete()
        db.commit()

    @staticmethod
    def get_file_count(source_id: int, db: Session) -> int:
        """Return the number of tracked files for a source."""
        return db.query(SharePointFile).filter(SharePointFile.source_id == source_id).count()
