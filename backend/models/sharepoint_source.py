import sqlalchemy as sa
from sqlalchemy import Column, Integer, String, Text, DateTime, JSON
from sqlalchemy.orm import relationship
from db.database import Base
from datetime import datetime

from models.enums.sharepoint_sync_status import SharePointSyncStatus


class SharePointSource(Base):
    """A SharePoint drive connection configured to sync files into a Silo."""
    __tablename__ = 'sharepoint_source'

    id = Column(Integer, primary_key=True, autoincrement=True)
    app_id = Column(Integer, sa.ForeignKey('App.app_id', ondelete='CASCADE'), nullable=False, index=True)
    silo_id = Column(Integer, sa.ForeignKey('Silo.silo_id'), nullable=False)

    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)

    # Microsoft credentials
    tenant_id = Column(String(255), nullable=False)
    client_id = Column(String(255), nullable=False)
    client_secret = Column(Text, nullable=False)

    # SharePoint site/drive references
    site_id = Column(String(255), nullable=False)
    site_name = Column(String(255), nullable=True)
    site_url = Column(Text, nullable=True)
    drive_id = Column(String(255), nullable=False)
    drive_name = Column(String(255), nullable=True)

    # Sync configuration
    file_extension_filters = Column(JSON, nullable=True, default=list)

    # Sync state
    last_delta_token = Column(Text, nullable=True)
    last_synced_at = Column(DateTime, nullable=True)
    last_sync_status = Column(
        sa.Enum(SharePointSyncStatus, name='sharepoint_sync_status', create_type=False),
        nullable=False,
        default=SharePointSyncStatus.IDLE,
        server_default='IDLE',
    )
    last_sync_error = Column(Text, nullable=True)

    # Scheduling
    refresh_interval_minutes = Column(Integer, nullable=True)
    next_run_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    app = relationship('App', back_populates='sharepoint_sources')
    silo = relationship('Silo', lazy=False, uselist=False)
    files = relationship('SharePointFile', back_populates='source', cascade='all, delete-orphan', lazy=True)
