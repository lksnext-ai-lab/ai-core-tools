import sqlalchemy as sa
from sqlalchemy import Column, Integer, String, Text, DateTime, UniqueConstraint
from sqlalchemy.orm import relationship
from db.database import Base
from datetime import datetime

from models.enums.domain_url_status import DomainUrlStatus
from models.enums.discovery_source import DiscoverySource


class DomainUrl(Base):
    """Discovered URL within a Domain — replaces the legacy Url model."""
    __tablename__ = 'domain_url'

    id = Column(Integer, primary_key=True, autoincrement=True)
    domain_id = Column(Integer, sa.ForeignKey('Domain.domain_id', ondelete='CASCADE'), nullable=False, index=True)

    url = Column(String(2048), nullable=False)
    normalized_url = Column(String(2048), nullable=False)

    status = Column(
        sa.Enum(DomainUrlStatus, name='domain_url_status', create_type=False),
        nullable=False,
        default=DomainUrlStatus.PENDING,
        server_default='PENDING',
    )
    discovered_via = Column(
        sa.Enum(DiscoverySource, name='discovery_source', create_type=False),
        nullable=False,
    )
    depth = Column(Integer, nullable=False, default=0, server_default='0')

    content_hash = Column(String(64), nullable=True)
    http_etag = Column(String(255), nullable=True)
    http_last_modified = Column(String(64), nullable=True)
    sitemap_lastmod = Column(DateTime, nullable=True)

    last_crawled_at = Column(DateTime, nullable=True)
    last_indexed_at = Column(DateTime, nullable=True)
    next_crawl_at = Column(DateTime, nullable=True)

    consecutive_skips = Column(Integer, nullable=False, default=0, server_default='0')
    failure_count = Column(Integer, nullable=False, default=0, server_default='0')
    last_error = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    domain = relationship('Domain', back_populates='urls')

    __table_args__ = (
        UniqueConstraint('domain_id', 'normalized_url', name='uq_domain_url_normalized'),
    )
