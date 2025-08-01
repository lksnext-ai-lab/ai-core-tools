from models.url import Url
from db.session import SessionLocal
from services.silo_service import SiloService
from datetime import datetime
from utils.logger import get_logger

logger = get_logger(__name__)

class UrlService:
    @staticmethod
    def get_url(url_id: int) -> Url:
        session = SessionLocal()
        try:
            return session.query(Url).filter(Url.url_id == url_id).first()
        finally:
            session.close()
    
    @staticmethod
    def create_url(url: str, domain_id: int) -> int:
        session = SessionLocal()
        try:
            url_obj = Url(url=url, domain_id=domain_id, status='pending')
            session.add(url_obj)
            session.commit()
            session.refresh(url_obj)  # Ensure we get the ID
            url_id = url_obj.url_id
            return url_id
        finally:
            session.close()
    
    @staticmethod
    def update_url_status(url_id: int, status: str, domain_id: int = None):
        """
        Update URL status and timestamp
        
        Args:
            url_id: ID of the URL to update
            status: New status ('pending', 'indexing', 'indexed', 'rejected')
            domain_id: Optional domain_id for validation
        """
        session = SessionLocal()
        try:
            query = session.query(Url).filter(Url.url_id == url_id)
            if domain_id:
                query = query.filter(Url.domain_id == domain_id)
            
            url = query.first()
            if url:
                url.status = status
                url.updated_at = datetime.now()
                session.commit()
                logger.info(f"Updated URL {url_id} status to {status}")
            else:
                logger.warning(f"URL {url_id} not found for status update")
        finally:
            session.close()
    
    @staticmethod
    def update_url_indexed(url_id: int, domain_id: int = None):
        """
        Mark URL as successfully indexed with timestamp
        """
        UrlService.update_url_status(url_id, 'indexed', domain_id)
    
    @staticmethod
    def update_url_rejected(url_id: int, domain_id: int = None):
        """
        Mark URL as rejected (failed indexing)
        """
        UrlService.update_url_status(url_id, 'rejected', domain_id)
    
    @staticmethod
    def update_url_indexing(url_id: int, domain_id: int = None):
        """
        Mark URL as currently being indexed
        """
        UrlService.update_url_status(url_id, 'indexing', domain_id)
    
    @staticmethod
    def unindex_url(url_id: int, domain_id: int = None):
        """
        Remove URL content from index and mark as unindexed
        """
        session = SessionLocal()
        try:
            query = session.query(Url).filter(Url.url_id == url_id)
            if domain_id:
                query = query.filter(Url.domain_id == domain_id)
            
            url = query.first()
            if url:
                # Remove content from silo if it exists
                domain = url.domain
                if domain and domain.silo_id:
                    full_url = domain.base_url + url.url
                    silo_service = SiloService()
                    silo_service.delete_url(domain.silo_id, full_url)
                    logger.info(f"Removed content from silo for URL: {full_url}")
                
                # Update status to unindexed
                url.status = 'unindexed'
                url.updated_at = datetime.now()
                session.commit()
                logger.info(f"Unindexed URL {url_id}")
            else:
                logger.warning(f"URL {url_id} not found for unindexing")
        finally:
            session.close()
    
    @staticmethod
    def reject_url(url_id: int, domain_id: int = None):
        """
        Mark URL as manually rejected (content not suitable for indexing)
        """
        session = SessionLocal()
        try:
            query = session.query(Url).filter(Url.url_id == url_id)
            if domain_id:
                query = query.filter(Url.domain_id == domain_id)
            
            url = query.first()
            if url:
                # Remove content from silo if it was previously indexed
                domain = url.domain
                if domain and domain.silo_id and url.status == 'indexed':
                    full_url = domain.base_url + url.url
                    silo_service = SiloService()
                    silo_service.delete_url(domain.silo_id, full_url)
                    logger.info(f"Removed indexed content for rejected URL: {full_url}")
                
                # Update status to rejected
                url.status = 'rejected'
                url.updated_at = datetime.now()
                session.commit()
                logger.info(f"Rejected URL {url_id}")
            else:
                logger.warning(f"URL {url_id} not found for rejection")
        finally:
            session.close()
    
    @staticmethod
    def delete_url(url_id: int, domain_id: int):
        """Delete URL and its indexed content"""
        session = SessionLocal()
        try:
            url = session.query(Url).filter(Url.url_id == url_id, Url.domain_id == domain_id).first()
            if url:
                # Get domain's silo to remove content
                domain = url.domain
                if domain and domain.silo_id:
                    silo_service = SiloService()
                    # Delete content from silo using URL as identifier
                    silo_service.delete_url(domain.silo_id, url.url)
                
                # Delete URL from database
                session.delete(url)
                session.commit()
        finally:
            session.close() 