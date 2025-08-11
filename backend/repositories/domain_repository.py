from typing import List, Optional, Tuple
from models.domain import Domain
from models.url import Url
from sqlalchemy.orm import Session
from utils.logger import get_logger

logger = get_logger(__name__)


class DomainRepository:
    """Repository for Domain data access operations"""
    
    @staticmethod
    def get_by_id(domain_id: int, db: Session) -> Optional[Domain]:
        """Get domain by ID"""
        return db.query(Domain).filter(Domain.domain_id == domain_id).first()
    
    @staticmethod
    def get_by_app_id(app_id: int, db: Session) -> List[Domain]:
        """Get all domains for a specific app"""
        return db.query(Domain).filter(Domain.app_id == app_id).all()
    
    @staticmethod
    def get_domains_with_url_counts(app_id: int, db: Session) -> List[Tuple[Domain, int]]:
        """Get all domains for a specific app with their URL counts"""
        # Import here to avoid circular imports
        from repositories.url_repository import UrlRepository
        
        # Use existing get_by_app_id method instead of duplicating query
        domains = DomainRepository.get_by_app_id(app_id, db)
        
        result = []
        for domain in domains:
            url_count = UrlRepository.count_by_domain(domain.domain_id, db)
            result.append((domain, url_count))
        
        return result
    
    @staticmethod
    def get_domain_with_urls_paginated(domain_id: int, db: Session, page: int = 1, per_page: int = 20) -> Tuple[Optional[Domain], List[Url], dict]:
        """Get a domain with its URLs with pagination"""
        # Import here to avoid circular imports
        from repositories.url_repository import UrlRepository
        
        # Use existing get_by_id method instead of duplicating query
        domain = DomainRepository.get_by_id(domain_id, db)
        if not domain:
            return None, [], {}
        
        # Use UrlRepository for URL operations
        urls, pagination_info = UrlRepository.get_by_domain_paginated(domain_id, db, page, per_page)
        
        return domain, urls, pagination_info
    
    @staticmethod
    def get_domain_detail_data(domain_id: int, db: Session) -> Optional[Tuple[Domain, int, Optional[int]]]:
        """Get domain with URL count and embedding service ID for detail view"""
        # Import here to avoid circular imports
        from repositories.url_repository import UrlRepository
        from repositories.silo_repository import SiloRepository
        
        # Use existing get_by_id method instead of duplicating query
        domain = DomainRepository.get_by_id(domain_id, db)
        if not domain:
            return None
        
        # Count URLs for this domain using UrlRepository
        url_count = UrlRepository.count_by_domain(domain.domain_id, db)
        
        # Get current embedding service ID from domain's silo using SiloRepository
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
        """Delete a domain and all its associated URLs"""
        # Use existing get_by_id method instead of duplicating query
        domain = DomainRepository.get_by_id(domain_id, db)
        if not domain:
            return False
        
        # Delete all URLs for this domain
        deleted_urls = db.query(Url).filter(Url.domain_id == domain_id).delete()
        logger.debug(f"Deleted {deleted_urls} URLs for domain {domain_id}")
        
        # Delete the domain itself
        db.delete(domain)
        db.commit()
        
        return True
