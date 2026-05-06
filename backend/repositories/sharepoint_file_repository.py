from typing import List, Optional
from sqlalchemy.orm import Session
from models.sharepoint_file import SharePointFile
from models.enums.sharepoint_file_status import SharePointFileStatus


class SharePointFileRepository:
    """Repository for SharePointFile data access operations."""

    @staticmethod
    def list_by_source(source_id: int, db: Session) -> List[SharePointFile]:
        """List all files for a source, ordered by creation date descending."""
        return (
            db.query(SharePointFile)
            .filter(SharePointFile.source_id == source_id)
            .order_by(SharePointFile.created_at.desc())
            .all()
        )

    @staticmethod
    def get_by_drive_item(source_id: int, drive_item_id: str, db: Session) -> Optional[SharePointFile]:
        """Fetch a file by its source and Microsoft drive item ID."""
        return (
            db.query(SharePointFile)
            .filter(
                SharePointFile.source_id == source_id,
                SharePointFile.drive_item_id == drive_item_id,
            )
            .first()
        )

    @staticmethod
    def upsert_by_drive_item(
        source_id: int,
        drive_item_id: str,
        data: dict,
        db: Session,
    ) -> SharePointFile:
        """Create or update a SharePointFile row identified by (source_id, drive_item_id)."""
        existing = SharePointFileRepository.get_by_drive_item(source_id, drive_item_id, db)
        updatable_fields = (
            'name', 'path', 'web_url', 'mime_type', 'size_bytes',
            'last_modified_at', 'status', 'last_synced_at', 'error_message', 'vector_doc_ids',
        )
        if existing:
            for field in updatable_fields:
                if field in data:
                    setattr(existing, field, data[field])
            db.add(existing)
            db.commit()
            db.refresh(existing)
            return existing
        else:
            new_file = SharePointFile(
                source_id=source_id,
                drive_item_id=drive_item_id,
                **{k: v for k, v in data.items() if k in updatable_fields},
            )
            db.add(new_file)
            db.commit()
            db.refresh(new_file)
            return new_file

    @staticmethod
    def delete_file(file_id: int, db: Session) -> None:
        """Delete a single file by ID."""
        db.query(SharePointFile).filter(SharePointFile.id == file_id).delete()
        db.commit()

    @staticmethod
    def delete_by_source(source_id: int, db: Session) -> None:
        """Bulk-delete all files for a source."""
        db.query(SharePointFile).filter(SharePointFile.source_id == source_id).delete()
        db.commit()

    @staticmethod
    def get_files_with_extension_not_in(
        source_id: int,
        allowed_extensions: List[str],
        db: Session,
    ) -> List[SharePointFile]:
        """Return files whose extension (case-insensitive) is NOT in the allowed list.

        Extensions in allowed_extensions must be provided without a leading dot (e.g. ['pdf', 'docx']).
        The comparison is case-insensitive; the file's extension is derived from its name.
        If allowed_extensions is empty, returns an empty list (no filter applied).
        """
        if not allowed_extensions:
            return []

        all_files = SharePointFileRepository.list_by_source(source_id, db)
        normalised_allowed = {ext.lower().lstrip('.') for ext in allowed_extensions}

        result = []
        for f in all_files:
            if not f.name:
                continue
            ext = f.name.rsplit('.', 1)[-1].lower() if '.' in f.name else ''
            if ext not in normalised_allowed:
                result.append(f)
        return result
