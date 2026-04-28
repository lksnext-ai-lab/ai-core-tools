from typing import List, Optional, Tuple
from datetime import datetime
from sqlalchemy.orm import Session
from models.domain_url import DomainUrl
from models.enums.domain_url_status import DomainUrlStatus
from models.enums.discovery_source import DiscoverySource
from utils.logger import get_logger

logger = get_logger(__name__)


class DomainUrlRepository:
    """Repository for DomainUrl data access operations."""

    @staticmethod
    def get_by_id(url_id: int, db: Session) -> Optional[DomainUrl]:
        return db.query(DomainUrl).filter(DomainUrl.id == url_id).first()

    @staticmethod
    def get_by_id_and_domain(url_id: int, domain_id: int, db: Session) -> Optional[DomainUrl]:
        return (
            db.query(DomainUrl)
            .filter(DomainUrl.id == url_id, DomainUrl.domain_id == domain_id)
            .first()
        )

    @staticmethod
    def get_by_domain_paginated(
        domain_id: int,
        db: Session,
        page: int = 1,
        per_page: int = 20,
        status: Optional[str] = None,
        discovered_via: Optional[str] = None,
        q: Optional[str] = None,
    ) -> Tuple[List[DomainUrl], dict]:
        query = db.query(DomainUrl).filter(DomainUrl.domain_id == domain_id)

        if status:
            query = query.filter(DomainUrl.status == status)
        if discovered_via:
            query = query.filter(DomainUrl.discovered_via == discovered_via)
        if q:
            query = query.filter(DomainUrl.url.ilike(f'%{q}%'))

        total = query.count()
        offset = (page - 1) * per_page
        items = query.offset(offset).limit(per_page).all()

        pagination_info = {
            'page': page,
            'per_page': per_page,
            'total': total,
            'pages': (total + per_page - 1) // per_page if per_page > 0 else 0,
        }
        return items, pagination_info

    @staticmethod
    def count_by_domain(domain_id: int, db: Session) -> int:
        return db.query(DomainUrl).filter(DomainUrl.domain_id == domain_id).count()

    @staticmethod
    def upsert(domain_id: int, normalized_url: str, defaults: dict, db: Session) -> DomainUrl:
        """Insert or update a DomainUrl. Uses query-then-create/update (portable across PG and SQLite)."""
        existing = (
            db.query(DomainUrl)
            .filter(DomainUrl.domain_id == domain_id, DomainUrl.normalized_url == normalized_url)
            .first()
        )
        if existing:
            for key, value in defaults.items():
                setattr(existing, key, value)
            db.commit()
            db.refresh(existing)
            return existing
        else:
            obj = DomainUrl(domain_id=domain_id, normalized_url=normalized_url, **defaults)
            db.add(obj)
            db.commit()
            db.refresh(obj)
            return obj

    @staticmethod
    def create(domain_url: DomainUrl, db: Session) -> DomainUrl:
        db.add(domain_url)
        db.commit()
        db.refresh(domain_url)
        return domain_url

    @staticmethod
    def update(domain_url: DomainUrl, db: Session) -> DomainUrl:
        db.add(domain_url)
        db.commit()
        db.refresh(domain_url)
        return domain_url

    @staticmethod
    def delete(domain_url: DomainUrl, db: Session) -> None:
        db.delete(domain_url)
        db.commit()

    @staticmethod
    def get_urls_due_for_crawl(domain_id: int, now: datetime, limit: int, db: Session) -> List[DomainUrl]:
        """
        Returns DomainUrl rows that are ready to be crawled:
        - status NOT IN (REMOVED, EXCLUDED, CRAWLING)
        - AND (next_crawl_at <= now OR (next_crawl_at IS NULL AND status == PENDING))
        """
        excluded_statuses = [DomainUrlStatus.REMOVED, DomainUrlStatus.EXCLUDED, DomainUrlStatus.CRAWLING]
        from sqlalchemy import or_, and_
        return (
            db.query(DomainUrl)
            .filter(
                DomainUrl.domain_id == domain_id,
                ~DomainUrl.status.in_(excluded_statuses),
                or_(
                    DomainUrl.next_crawl_at <= now,
                    and_(
                        DomainUrl.next_crawl_at.is_(None),
                        DomainUrl.status == DomainUrlStatus.PENDING,
                    ),
                ),
            )
            .limit(limit)
            .all()
        )
