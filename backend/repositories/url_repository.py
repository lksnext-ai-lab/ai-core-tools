from models.url import Url
from datetime import datetime
from sqlalchemy.orm import Session
from typing import Optional

class UrlRepository:
    """Repository for URL data access operations"""
    
    @staticmethod
    def get_by_id(url_id: int, db: Session) -> Optional[Url]:
        """Get URL by ID"""
        return db.query(Url).filter(Url.url_id == url_id).first()
    
    @staticmethod
    def get_by_id_and_domain(url_id: int, domain_id: int, db: Session) -> Optional[Url]:
        """Get URL by ID and domain ID"""
        return db.query(Url).filter(
            Url.url_id == url_id, 
            Url.domain_id == domain_id
        ).first()
    
    @staticmethod
    def create(url: str, domain_id: int, db: Session) -> Url:
        """Create a new URL"""
        url_obj = Url(url=url, domain_id=domain_id, status='pending')
        db.add(url_obj)
        db.commit()
        db.refresh(url_obj)
        return url_obj
    
    @staticmethod
    def update_status(url_id: int, status: str, db: Session, domain_id: int = None) -> bool:
        """Update URL status and timestamp"""
        query = db.query(Url).filter(Url.url_id == url_id)
        if domain_id:
            query = query.filter(Url.domain_id == domain_id)
        
        url = query.first()
        if url:
            url.status = status
            url.updated_at = datetime.now()
            db.commit()
            return True
        return False
    
    @staticmethod
    def update_url_object(url: Url, db: Session) -> None:
        """Update an existing URL object"""
        url.updated_at = datetime.now()
        db.commit()
    
    @staticmethod
    def delete(url: Url, db: Session) -> None:
        """Delete a URL from database"""
        db.delete(url)
        db.commit()
    
    @staticmethod
    def count_by_domain(domain_id: int, db: Session) -> int:
        """Count URLs by domain ID"""
        return db.query(Url).filter(Url.domain_id == domain_id).count()
    
    @staticmethod
    def get_by_domain_paginated(domain_id: int, db: Session, page: int = 1, per_page: int = 20) -> tuple:
        """Get URLs by domain with pagination"""
        # Get total count
        total_urls = db.query(Url).filter(Url.domain_id == domain_id).count()
        
        # Get URLs for current page
        offset = (page - 1) * per_page
        urls = db.query(Url).filter(Url.domain_id == domain_id).offset(offset).limit(per_page).all()
        
        pagination_info = {
            'page': page,
            'per_page': per_page,
            'total': total_urls,
            'has_prev': page > 1,
            'has_next': (page * per_page) < total_urls,
            'prev_num': page - 1 if page > 1 else None,
            'next_num': page + 1 if (page * per_page) < total_urls else None
        }
        
        return urls, pagination_info
