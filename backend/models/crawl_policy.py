import sqlalchemy as sa
from sqlalchemy import Column, Integer, String, Boolean, Float
from sqlalchemy.orm import relationship
from db.database import Base
from datetime import datetime


class CrawlPolicy(Base):
    """1:1 crawl policy per Domain — declares how URLs are discovered and refreshed."""
    __tablename__ = 'crawl_policy'

    id = Column(Integer, primary_key=True, autoincrement=True)
    domain_id = Column(Integer, sa.ForeignKey('Domain.domain_id', ondelete='CASCADE'), nullable=False, unique=True)

    seed_url = Column(String(2048), nullable=True)
    sitemap_url = Column(String(2048), nullable=True)

    # Use default=list (not default=[]) to avoid shared mutable default
    manual_urls = Column(sa.JSON, nullable=False, default=list)
    max_depth = Column(Integer, nullable=False, default=2)
    include_globs = Column(sa.JSON, nullable=False, default=list)
    exclude_globs = Column(sa.JSON, nullable=False, default=list)

    rate_limit_rps = Column(Float, nullable=False, default=1.0)
    refresh_interval_hours = Column(Integer, nullable=False, default=168)
    respect_robots_txt = Column(Boolean, nullable=False, default=True)
    is_active = Column(Boolean, nullable=False, default=True)

    created_at = Column(sa.DateTime, default=datetime.utcnow)
    updated_at = Column(sa.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    domain = relationship('Domain', back_populates='crawl_policy')
