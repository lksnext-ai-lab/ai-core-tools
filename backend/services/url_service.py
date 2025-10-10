from models.url import Url
from repositories.url_repository import UrlRepository
from services.silo_service import SiloService
from utils.logger import get_logger
from sqlalchemy.orm import Session
from typing import Optional

logger = get_logger(__name__)

class UrlService:
    """Service layer for URL business logic"""
    
    @staticmethod
    def get_url(url_id: int, db: Session) -> Optional[Url]:
        """Get URL by ID"""
        return UrlRepository.get_by_id(url_id, db)
    
    @staticmethod
    def create_url(url: str, domain_id: int, db: Session) -> int:
        """Create a new URL and return its ID"""
        url_obj = UrlRepository.create(url, domain_id, db)
        logger.info(f"Created URL {url_obj.url_id} for domain {domain_id}")
        return url_obj.url_id
    
    @staticmethod
    def update_url_status(url_id: int, status: str, db: Session, domain_id: int = None) -> bool:
        """
        Update URL status and timestamp
        
        Args:
            url_id: ID of the URL to update
            status: New status ('pending', 'indexing', 'indexed', 'rejected')
            db: Database session
            domain_id: Optional domain_id for validation
            
        Returns:
            bool: True if URL was updated, False if not found
        """
        success = UrlRepository.update_status(url_id, status, db, domain_id)
        if success:
            logger.info(f"Updated URL {url_id} status to {status}")
        else:
            logger.warning(f"URL {url_id} not found for status update")
        return success
    
    @staticmethod
    def update_url_indexed(url_id: int, db: Session, domain_id: int = None) -> bool:
        """Mark URL as successfully indexed with timestamp"""
        return UrlService.update_url_status(url_id, 'indexed', db, domain_id)
    
    @staticmethod
    def update_url_rejected(url_id: int, db: Session, domain_id: int = None) -> bool:
        """Mark URL as rejected (failed indexing)"""
        return UrlService.update_url_status(url_id, 'rejected', db, domain_id)
    
    @staticmethod
    def update_url_indexing(url_id: int, db: Session, domain_id: int = None) -> bool:
        """Mark URL as currently being indexed"""
        return UrlService.update_url_status(url_id, 'indexing', db, domain_id)
    
    @staticmethod
    def unindex_url(url_id: int, db: Session, domain_id: int = None) -> bool:
        """
        Remove URL content from index and mark as unindexed
        
        Returns:
            bool: True if URL was found and unindexed, False if not found
        """
        url = UrlRepository.get_by_id_and_domain(url_id, domain_id, db) if domain_id else UrlRepository.get_by_id(url_id, db)
        
        if url:
            # Remove content from silo if it exists
            domain = url.domain
            if domain and domain.silo_id:
                full_url = domain.base_url + url.url
                SiloService.delete_url(domain.silo_id, full_url, db)
                logger.info(f"Removed content from silo for URL: {full_url}")
            
            # Update status to unindexed
            url.status = 'unindexed'
            UrlRepository.update_url_object(url, db)
            logger.info(f"Unindexed URL {url_id}")
            return True
        else:
            logger.warning(f"URL {url_id} not found for unindexing")
            return False
    
    @staticmethod
    def reject_url(url_id: int, db: Session, domain_id: int = None) -> bool:
        """
        Mark URL as manually rejected (content not suitable for indexing)
        
        Returns:
            bool: True if URL was found and rejected, False if not found
        """
        url = UrlRepository.get_by_id_and_domain(url_id, domain_id, db) if domain_id else UrlRepository.get_by_id(url_id, db)
        
        if url:
            # Remove content from silo if it was previously indexed
            domain = url.domain
            if domain and domain.silo_id and url.status == 'indexed':
                full_url = domain.base_url + url.url
                SiloService.delete_url(domain.silo_id, full_url, db)
                logger.info(f"Removed indexed content for rejected URL: {full_url}")
            
            # Update status to rejected
            url.status = 'rejected'
            UrlRepository.update_url_object(url, db)
            logger.info(f"Rejected URL {url_id}")
            return True
        else:
            logger.warning(f"URL {url_id} not found for rejection")
            return False
    
    @staticmethod
    def delete_url(url_id: int, domain_id: int, db: Session) -> bool:
        """
        Delete URL and its indexed content
        
        Returns:
            bool: True if URL was found and deleted, False if not found
        """
        url = UrlRepository.get_by_id_and_domain(url_id, domain_id, db)
        
        if url:
            # Get domain's silo to remove content
            domain = url.domain
            if domain and domain.silo_id:
                full_url = domain.base_url + url.url
                SiloService.delete_url(domain.silo_id, full_url, db)
                logger.info(f"Removed content from silo for deleted URL: {full_url}")
            
            # Delete URL from database
            UrlRepository.delete(url, db)
            logger.info(f"Deleted URL {url_id} from domain {domain_id}")
            return True
        else:
            logger.warning(f"URL {url_id} not found in domain {domain_id} for deletion")
            return False 