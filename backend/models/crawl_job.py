import sqlalchemy as sa
from sqlalchemy import Column, Integer, String, Text, DateTime
from sqlalchemy.orm import relationship
from db.database import Base
from datetime import datetime

from models.enums.crawl_job_status import CrawlJobStatus
from models.enums.crawl_trigger import CrawlTrigger


class CrawlJob(Base):
    """A single crawl execution for a Domain — queued, run by a worker, and tracked here."""
    __tablename__ = 'crawl_job'

    id = Column(Integer, primary_key=True, autoincrement=True)
    domain_id = Column(Integer, sa.ForeignKey('Domain.domain_id', ondelete='CASCADE'), nullable=False, index=True)

    status = Column(
        sa.Enum(CrawlJobStatus, name='crawl_job_status', create_type=False),
        nullable=False,
        default=CrawlJobStatus.QUEUED,
        server_default='QUEUED',
    )
    triggered_by = Column(
        sa.Enum(CrawlTrigger, name='crawl_trigger', create_type=False),
        nullable=False,
    )
    triggered_by_user_id = Column(Integer, sa.ForeignKey('User.user_id'), nullable=True)

    started_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)

    discovered_count = Column(Integer, nullable=False, default=0)
    indexed_count = Column(Integer, nullable=False, default=0)
    skipped_count = Column(Integer, nullable=False, default=0)
    removed_count = Column(Integer, nullable=False, default=0)
    failed_count = Column(Integer, nullable=False, default=0)

    error_log = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    worker_id = Column(String(64), nullable=True)
    heartbeat_at = Column(DateTime, nullable=True)

    domain = relationship('Domain', back_populates='crawl_jobs')
