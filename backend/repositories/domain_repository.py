from typing import List, Optional, Tuple
from models.domain import Domain
from models.domain_url import DomainUrl
from sqlalchemy.orm import Session, joinedload
from utils.logger import get_logger

logger = get_logger(__name__)


class DomainRepository:
    """Repository for Domain data access operations"""

    @staticmethod
    def get_by_id(domain_id: int, db: Session) -> Optional[Domain]:
        """Get domain by ID"""
        return (
            db.query(Domain)
            .options(joinedload(Domain.silo))
            .filter(Domain.domain_id == domain_id)
            .first()
        )

    @staticmethod
    def get_by_app_id(app_id: int, db: Session) -> List[Domain]:
        """Get all domains for a specific app"""
        return (
            db.query(Domain)
            .options(joinedload(Domain.silo))
            .filter(Domain.app_id == app_id)
            .all()
        )

    @staticmethod
    def get_domains_with_url_counts(app_id: int, db: Session) -> List[Tuple[Domain, int]]:
        """Get all domains for a specific app with their URL counts"""
        domains = DomainRepository.get_by_app_id(app_id, db)

        result = []
        for domain in domains:
            url_count = db.query(DomainUrl).filter(DomainUrl.domain_id == domain.domain_id).count()
            result.append((domain, url_count))

        return result

    @staticmethod
    def get_domain_with_urls_paginated(domain_id: int, db: Session, page: int = 1, per_page: int = 20) -> Tuple[Optional[Domain], List[DomainUrl], dict]:
        """Get a domain with its DomainUrl rows with pagination"""
        domain = DomainRepository.get_by_id(domain_id, db)
        if not domain:
            return None, [], {}

        offset = (page - 1) * per_page
        total = db.query(DomainUrl).filter(DomainUrl.domain_id == domain_id).count()
        urls = (
            db.query(DomainUrl)
            .filter(DomainUrl.domain_id == domain_id)
            .offset(offset)
            .limit(per_page)
            .all()
        )
        pagination_info = {
            'page': page,
            'per_page': per_page,
            'total': total,
            'pages': (total + per_page - 1) // per_page if per_page > 0 else 0,
        }
        return domain, urls, pagination_info

    @staticmethod
    def get_domain_detail_data(domain_id: int, db: Session) -> Optional[Tuple[Domain, int, Optional[int]]]:
        """Get domain with URL count and embedding service ID for detail view"""
        from repositories.silo_repository import SiloRepository

        domain = DomainRepository.get_by_id(domain_id, db)
        if not domain:
            return None

        url_count = db.query(DomainUrl).filter(DomainUrl.domain_id == domain_id).count()

        embedding_service_id = None
        if domain.silo_id:
            silo = SiloRepository.get_by_id(domain.silo_id, db)
            if silo and silo.embedding_service_id:
                embedding_service_id = silo.embedding_service_id

        return domain, url_count, embedding_service_id

    @staticmethod
    def create(domain: Domain, db: Session) -> Domain:
        """Create a new domain"""
        db.add(domain)
        db.commit()
        db.refresh(domain)
        return domain

    @staticmethod
    def update(domain: Domain, db: Session) -> Domain:
        """Update an existing domain"""
        db.add(domain)
        db.commit()
        db.refresh(domain)
        return domain

    @staticmethod
    def delete_with_urls(domain_id: int, db: Session) -> bool:
        """Delete a domain and all its associated resources (cascade handles DomainUrl, CrawlPolicy, CrawlJob)."""
        domain = DomainRepository.get_by_id(domain_id, db)
        if not domain:
            return False

        db.delete(domain)
        db.commit()

        return True
