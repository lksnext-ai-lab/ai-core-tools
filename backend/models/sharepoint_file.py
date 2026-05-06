import sqlalchemy as sa
from sqlalchemy import Column, Integer, String, Text, DateTime, BigInteger, JSON, UniqueConstraint
from sqlalchemy.orm import relationship
from db.database import Base
from datetime import datetime

from models.enums.sharepoint_file_status import SharePointFileStatus


class SharePointFile(Base):
    """A file tracked within a SharePoint drive sync operation."""
    __tablename__ = 'sharepoint_file'

    __table_args__ = (
        UniqueConstraint('source_id', 'drive_item_id', name='uq_spfile_source_item'),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    source_id = Column(Integer, sa.ForeignKey('sharepoint_source.id', ondelete='CASCADE'), nullable=False, index=True)

    drive_item_id = Column(String(512), nullable=False)
    name = Column(String(512), nullable=True)
    path = Column(Text, nullable=True)
    web_url = Column(Text, nullable=True)
    mime_type = Column(String(255), nullable=True)
    size_bytes = Column(BigInteger, nullable=True)
    last_modified_at = Column(DateTime, nullable=True)

    status = Column(
        sa.Enum(SharePointFileStatus, name='sharepoint_file_status', create_type=False),
        nullable=False,
        default=SharePointFileStatus.PENDING,
        server_default='PENDING',
    )
    last_synced_at = Column(DateTime, nullable=True)
    error_message = Column(Text, nullable=True)
    vector_doc_ids = Column(JSON, nullable=True, default=list)

    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    source = relationship('SharePointSource', back_populates='files')
