from model.user import User
from model.app import App
from model.api_key import APIKey
from extensions import db
from sqlalchemy.orm import joinedload
from typing import List, Optional
import logging

logger = logging.getLogger(__name__)

class UserService:
    
    @staticmethod
    def get_all_users(page: int = 1, per_page: int = 10) -> tuple[List[User], int]:
        """Get all users with pagination"""
        users_query = db.session.query(User).options(
            joinedload(User.apps),
            joinedload(User.api_keys)
        )
        total = users_query.count()
        offset = (page - 1) * per_page
        users = users_query.offset(offset).limit(per_page).all()
        return users, total
    
    @staticmethod
    def get_user_by_id(user_id: int) -> Optional[User]:
        """Get user by ID with related data"""
        return db.session.query(User).options(
            joinedload(User.apps),
            joinedload(User.api_keys)
        ).filter(User.user_id == user_id).first()
    
    @staticmethod
    def get_user_by_email(email: str) -> Optional[User]:
        """Get user by email"""
        return db.session.query(User).filter(User.email == email).first()
    
    @staticmethod
    def create_user(user_data: dict) -> User:
        """Create a new user"""
        user = User(**user_data)
        db.session.add(user)
        db.session.commit()
        logger.info(f"Created new user: {user.email}")
        return user
    
    @staticmethod
    def update_user(user_id: int, user_data: dict) -> Optional[User]:
        """Update user information"""
        user = UserService.get_user_by_id(user_id)
        if not user:
            return None
        
        for key, value in user_data.items():
            if hasattr(user, key):
                setattr(user, key, value)
        
        db.session.commit()
        logger.info(f"Updated user: {user.email}")
        return user
    
    @staticmethod
    def delete_user(user_id: int) -> bool:
        """Delete user and all associated data (apps, API keys, etc.)"""
        try:
            user = UserService.get_user_by_id(user_id)
            if not user:
                logger.warning(f"User with ID {user_id} not found")
                return False
            
            user_email = user.email
            
            # Delete all user's apps using AppService (this will cascade to all related entities)
            apps_count = len(user.apps)
            if apps_count > 0:
                # Get app IDs before deletion for logging
                app_ids = [app.app_id for app in user.apps]
                
                # Import AppService here to avoid circular imports
                from services.app_service import AppService
                
                # Delete each app using AppService which handles proper cascading
                # This will also delete all associated API keys, agents, repositories, etc.
                for app in user.apps[:]:  # Use slice copy to avoid modification during iteration
                    AppService.delete_app(app.app_id)
                
                logger.info(f"Deleted {apps_count} apps (IDs: {app_ids}) and all associated data for user {user_email}")
            
            # Finally delete the user
            db.session.delete(user)
            db.session.commit()
            
            logger.info(f"Successfully deleted user: {user_email}")
            return True
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error deleting user {user_id}: {str(e)}")
            raise e
    
    @staticmethod
    def get_user_stats() -> dict:
        """Get user statistics for admin dashboard"""
        total_users = db.session.query(User).count()
        
        # Get recent users (last 10)
        recent_users = db.session.query(User).order_by(User.create_date.desc()).limit(10).all()
        
        # Get users with most apps
        from sqlalchemy import func
        users_with_apps = db.session.query(
            User.name, 
            User.email, 
            func.count(App.app_id).label('app_count')
        ).join(App).group_by(User.user_id, User.name, User.email).order_by(
            func.count(App.app_id).desc()
        ).limit(5).all()
        
        return {
            'total_users': total_users,
            'recent_users': recent_users,
            'users_with_apps': users_with_apps
        }
    
    @staticmethod
    def search_users(query: str, page: int = 1, per_page: int = 10) -> tuple[List[User], int]:
        """Search users by name or email"""
        search_filter = f"%{query}%"
        users_query = db.session.query(User).filter(
            db.or_(
                User.name.ilike(search_filter),
                User.email.ilike(search_filter)
            )
        ).options(
            joinedload(User.apps),
            joinedload(User.api_keys)
        )
        
        total = users_query.count()
        offset = (page - 1) * per_page
        users = users_query.offset(offset).limit(per_page).all()
        return users, total 