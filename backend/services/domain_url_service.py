"""Service for DomainUrl management. Replaces the legacy UrlService."""
from typing import List, Optional, Tuple
from datetime import datetime
from sqlalchemy.orm import Session

from models.domain_url import DomainUrl
from models.enums.domain_url_status import DomainUrlStatus
from models.enums.discovery_source import DiscoverySource
from repositories.domain_url_repository import DomainUrlRepository
from repositories.domain_repository import DomainRepository
from services.crawl.normalization import normalize_url
from utils.logger import get_logger

logger = get_logger(__name__)


class DomainUrlService:
    """Service for managing DomainUrl records."""

    @staticmethod
    def get_url(url_id: int, db: Session) -> Optional[DomainUrl]:
        """Get a single DomainUrl by ID."""
        return DomainUrlRepository.get_by_id(url_id, db)

    @staticmethod
    def list_urls(
        domain_id: int,
        db: Session,
        page: int = 1,
        per_page: int = 20,
        status: Optional[str] = None,
        discovered_via: Optional[str] = None,
        q: Optional[str] = None,
    ) -> Tuple[List[DomainUrl], dict]:
        """List DomainUrl rows for a domain with optional filters and pagination."""
        return DomainUrlRepository.get_by_domain_paginated(
            domain_id=domain_id,
            db=db,
            page=page,
            per_page=per_page,
            status=status,
            discovered_via=discovered_via,
            q=q,
        )

    @staticmethod
    def count_urls(domain_id: int, db: Session) -> int:
        """Count DomainUrl rows for a domain."""
        return DomainUrlRepository.count_by_domain(domain_id, db)

    @staticmethod
    def add_manual_url(url: str, domain_id: int, db: Session) -> DomainUrl:
        """
        Normalize the URL and upsert a PENDING MANUAL DomainUrl row.
        Returns the existing row if already present (upsert semantics).
        """
        norm = normalize_url(url)
        return DomainUrlRepository.upsert(
            domain_id=domain_id,
            normalized_url=norm,
            defaults={
                'url': url,
                'discovered_via': DiscoverySource.MANUAL,
                'status': DomainUrlStatus.PENDING,
                'depth': 0,
            },
            db=db,
        )

    @staticmethod
    def delete_url(url_id: int, domain_id: int, db: Session) -> bool:
        """
        Delete a DomainUrl. If the domain has a silo, also removes the content from the vector store.
        Returns True if found and deleted, False if not found.
        """
        domain_url = DomainUrlRepository.get_by_id_and_domain(url_id, domain_id, db)
        if not domain_url:
            return False

        # Remove from silo if present
        domain = DomainRepository.get_by_id(domain_id, db)
        if domain and domain.silo_id:
            try:
                from services.silo_service import SiloService
                SiloService.delete_url(domain.silo_id, domain_url.url, db)
            except Exception as e:
                logger.warning(f"Failed to delete URL {domain_url.url} from silo: {e}")

        DomainUrlRepository.delete(domain_url, db)
        return True

    @staticmethod
    def mark_for_recrawl(url_id: int, domain_id: int, db: Session) -> bool:
        """
        Mark a DomainUrl for immediate recrawl by setting next_crawl_at=now and status=PENDING.
        Returns True if found, False otherwise.
        """
        domain_url = DomainUrlRepository.get_by_id_and_domain(url_id, domain_id, db)
        if not domain_url:
            return False

        domain_url.next_crawl_at = datetime.utcnow()
        domain_url.status = DomainUrlStatus.PENDING
        db.commit()
        return True
