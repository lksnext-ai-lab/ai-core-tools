from model.url import Url
from extensions import db
from services.silo_service import SiloService

class UrlService:
    @staticmethod
    def get_url(url_id: int) -> Url:
        return db.session.query(Url).filter(Url.url_id == url_id).first()
    
    @staticmethod
    def create_url(url: str, domain_id: int) -> Url:
        url = Url(url=url, domain_id=domain_id)
        db.session.add(url)
        db.session.commit()
        return url
    
    @staticmethod
    def delete_url(url_id: int, domain_id: int):
        """Delete URL and its indexed content"""
        url = db.session.query(Url).filter(Url.url_id == url_id, Url.domain_id == domain_id).first()
        if url:
            # Get domain's silo to remove content
            domain = url.domain
            if domain and domain.silo_id:
                silo_service = SiloService()
                # Delete content from silo using URL as identifier
                silo_service.delete_url(domain.silo_id, url.url)
            
            # Delete URL from database
            db.session.delete(url)
            db.session.commit()


