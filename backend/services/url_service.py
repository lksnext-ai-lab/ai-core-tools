from models.url import Url
from db.session import SessionLocal
from services.silo_service import SiloService

class UrlService:
    @staticmethod
    def get_url(url_id: int) -> Url:
        session = SessionLocal()
        try:
            return session.query(Url).filter(Url.url_id == url_id).first()
        finally:
            session.close()
    
    @staticmethod
    def create_url(url: str, domain_id: int) -> Url:
        session = SessionLocal()
        try:
            url_obj = Url(url=url, domain_id=domain_id)
            session.add(url_obj)
            session.commit()
            return url_obj
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