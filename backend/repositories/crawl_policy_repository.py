from typing import List, Optional
from sqlalchemy.orm import Session
from models.crawl_policy import CrawlPolicy
from utils.logger import get_logger

logger = get_logger(__name__)


class CrawlPolicyRepository:
    """Repository for CrawlPolicy data access operations."""

    @staticmethod
    def get_by_domain(domain_id: int, db: Session) -> Optional[CrawlPolicy]:
        return db.query(CrawlPolicy).filter(CrawlPolicy.domain_id == domain_id).first()

    @staticmethod
    def create(policy: CrawlPolicy, db: Session) -> CrawlPolicy:
        db.add(policy)
        db.commit()
        db.refresh(policy)
        return policy

    @staticmethod
    def update(policy: CrawlPolicy, db: Session) -> CrawlPolicy:
        db.add(policy)
        db.commit()
        db.refresh(policy)
        return policy

    @staticmethod
    def get_domains_due_for_schedule(db: Session) -> List[CrawlPolicy]:
        """Returns active policies that could be scheduled (refresh_interval_hours > 0)."""
        return (
            db.query(CrawlPolicy)
            .filter(
                CrawlPolicy.is_active.is_(True),
                CrawlPolicy.refresh_interval_hours > 0,
            )
            .all()
        )
