from app.model.url import Url
from app.extensions import db

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
    
    
