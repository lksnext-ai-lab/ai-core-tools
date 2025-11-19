from typing import Optional, List, Tuple
from sqlalchemy.orm import Session, joinedload
from models.user import User
from models.app import App
from sqlalchemy import or_
from datetime import datetime, timedelta, timezone
from utils.logger import get_logger

logger = get_logger(__name__)

class UserRepository:
    
    def __init__(self, db: Session):
        self.db = db
    
    def get_by_id(self, user_id: int) -> Optional[User]:
        """Get user by ID"""
        if not user_id or user_id <= 0:
            return None
        return self.db.query(User).filter(User.user_id == user_id).first()
    
    def get_by_id_with_relations(self, user_id: int) -> Optional[User]:
        """Get user by ID with related data"""
        if not user_id or user_id <= 0:
            return None
        return self.db.query(User).options(
            joinedload(User.owned_apps),
            joinedload(User.api_keys)
        ).filter(User.user_id == user_id).first()
    
    def get_by_email(self, email: str) -> Optional[User]:
        """Get user by email"""
        return self.db.query(User).filter(User.email == email).first()
    
    def create(self, email: str, name: str = None) -> User:
        """Create a new user"""
        new_user = User(
            email=email,
            name=name
        )
        self.db.add(new_user)
        self.db.commit()
        self.db.refresh(new_user)
        return new_user
    
    def update(self, user: User, name: str = None) -> User:
        """Update user information"""
        if name and user.name != name:
            user.name = name
            self.db.commit()
            self.db.refresh(user)
        return user
    
    def delete(self, user_id: int) -> bool:
        """Delete a user and all associated data"""
        try:
            user = self.db.query(User).filter(User.user_id == user_id).first()
            if not user:
                return False
            
            # Delete user (cascade will handle related data)
            self.db.delete(user)
            self.db.commit()
            return True
        except Exception as e:
            logger.error(f"Error deleting user {user_id}: {e}")
            self.db.rollback()
            raise e
    
    def get_all_paginated(self, page: int = 1, per_page: int = 10) -> Tuple[List[User], int]:
        """Get all users with pagination"""
        if page < 1:
            page = 1
        if per_page < 1 or per_page > 100:
            per_page = 10
        
        users_query = self.db.query(User).options(
            joinedload(User.owned_apps),
            joinedload(User.api_keys)
        )
        total = users_query.count()
        offset = (page - 1) * per_page
        users = users_query.offset(offset).limit(per_page).all()
        
        return users, total
    
    def search_users(self, query: str, page: int = 1, per_page: int = 10) -> Tuple[List[User], int]:
        """Search users by name or email"""
        if page < 1:
            page = 1
        if per_page < 1 or per_page > 100:
            per_page = 10
        
        users_query = self.db.query(User).options(
            joinedload(User.owned_apps),
            joinedload(User.api_keys)
        ).filter(
            or_(
                User.name.ilike(f'%{query}%'),
                User.email.ilike(f'%{query}%')
            )
        )
        total = users_query.count()
        offset = (page - 1) * per_page
        users = users_query.offset(offset).limit(per_page).all()
        
        return users, total
    
    def get_total_count(self) -> int:
        """Get total users count"""
        return self.db.query(User).count()
    
    def get_recent_users_count(self, days: int = 30) -> int:
        """Get count of recent users (last N days)"""
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)
        return self.db.query(User).filter(
            User.create_date >= cutoff_date
        ).count()
    
    def get_users_with_apps_count(self) -> int:
        """Get count of users with apps"""
        return self.db.query(User).join(App).distinct().count()
    
    def get_recent_users_list(self, days: int = 30, limit: int = 10) -> List[User]:
        """Get recent users list (last N days)"""
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)
        return self.db.query(User).filter(
            User.create_date >= cutoff_date
        ).order_by(User.create_date.desc()).limit(limit).all()
