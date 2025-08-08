from sqlalchemy.orm import Session, joinedload
from models.user import User
from models.app import App
from models.api_key import APIKey
from db.database import SessionLocal
from typing import Tuple, List, Dict, Any
from sqlalchemy import func, or_

class UserService:
    
    @staticmethod
    def get_or_create_user(email: str, name: str = None) -> Tuple[User, bool]:
        """
        Get existing user or create new user if doesn't exist.
        Returns: (user, created) where created is True if user was just created
        """
        session = SessionLocal()
        try:
            # Try to find existing user
            user = session.query(User).filter(User.email == email).first()
            
            if user:
                # User exists, update name if provided and different
                if name and user.name != name:
                    user.name = name
                    session.commit()
                    session.refresh(user)
                return user, False
            
            # Create new user
            new_user = User(
                email=email,
                name=name
            )
            session.add(new_user)
            session.commit()
            session.refresh(new_user)
            
            return new_user, True
            
        finally:
            session.close()
    
    @staticmethod
    def get_user_by_id(user_id: int) -> User:
        """Get user by ID"""
        session = SessionLocal()
        try:
            return session.query(User).filter(User.user_id == user_id).first()
        finally:
            session.close()
    
    @staticmethod
    def get_user_by_email(email: str) -> User:
        """Get user by email"""
        session = SessionLocal()
        try:
            return session.query(User).filter(User.email == email).first()
        finally:
            session.close()
    
    @staticmethod
    def get_user_accessible_apps(user_id: int):
        """Get all apps user has access to (owned + collaborated)"""
        # TODO: Implement this method
        pass
    
    @staticmethod
    def get_user_subscription(user_id: int):
        """Get user's current active subscription"""
        # TODO: Implement this method
        pass
    
    @staticmethod
    def get_user_current_plan(user_id: int):
        """Get user's current active plan"""
        # TODO: Implement this method
        pass
    
    @staticmethod
    def can_user_create_agent(user_id: int) -> bool:
        """Check if user can create more agents"""
        # TODO: Implement this method
        return True  # For now, allow all users
    
    @staticmethod
    def can_user_create_domain(user_id: int) -> bool:
        """Check if user can create more domains"""
        # TODO: Implement this method
        return True  # For now, allow all users
    
    @staticmethod
    def user_has_feature(user_id: int, feature_name: str) -> bool:
        """Check if user has access to a specific feature"""
        # TODO: Implement this method
        return True  # For now, allow all features
    
    # ============================================================================
    # ADMIN METHODS
    # ============================================================================
    
    @staticmethod
    def get_all_users(page: int = 1, per_page: int = 10, db: Session = None) -> Tuple[List[Dict], int]:
        """
        Get all users with pagination
        
        Args:
            page: Page number (1-based)
            per_page: Number of users per page
            db: Database session (optional)
            
        Returns:
            Tuple of (users_list, total_count)
        """
        if page < 1:
            page = 1
        if per_page < 1 or per_page > 100:
            per_page = 10
        
        session = db or SessionLocal()
        try:
            users_query = session.query(User).options(
                joinedload(User.owned_apps),
                joinedload(User.api_keys)
            )
            total = users_query.count()
            offset = (page - 1) * per_page
            users = users_query.offset(offset).limit(per_page).all()
            
            # Convert to dict format
            users_list = []
            for user in users:
                users_list.append({
                    'user_id': user.user_id,
                    'email': user.email,
                    'name': user.name,
                    'created_at': user.create_date.isoformat() if user.create_date else None,
                    'owned_apps_count': len(user.owned_apps) if user.owned_apps else 0,
                    'api_keys_count': len(user.api_keys) if user.api_keys else 0
                })
            
            return users_list, total
        finally:
            if not db:
                session.close()
    
    @staticmethod
    def get_user_by_id(user_id: int, db: Session = None) -> User:
        """
        Get user by ID with related data
        
        Args:
            user_id: ID of the user
            db: Database session (optional)
            
        Returns:
            User instance or None if not found
        """
        if not user_id or user_id <= 0:
            return None
        
        session = db or SessionLocal()
        try:
            return session.query(User).options(
                joinedload(User.owned_apps),
                joinedload(User.api_keys)
            ).filter(User.user_id == user_id).first()
        finally:
            if not db:
                session.close()
    
    @staticmethod
    def search_users(query: str, page: int = 1, per_page: int = 10, db: Session = None) -> Tuple[List[Dict], int]:
        """
        Search users by name or email
        
        Args:
            query: Search query
            page: Page number (1-based)
            per_page: Number of users per page
            db: Database session (optional)
            
        Returns:
            Tuple of (users_list, total_count)
        """
        if page < 1:
            page = 1
        if per_page < 1 or per_page > 100:
            per_page = 10
        
        session = db or SessionLocal()
        try:
            users_query = session.query(User).options(
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
            
            # Convert to dict format
            users_list = []
            for user in users:
                users_list.append({
                    'user_id': user.user_id,
                    'email': user.email,
                    'name': user.name,
                    'created_at': user.create_date.isoformat() if user.create_date else None,
                    'owned_apps_count': len(user.owned_apps) if user.owned_apps else 0,
                    'api_keys_count': len(user.api_keys) if user.api_keys else 0
                })
            
            return users_list, total
        finally:
            if not db:
                session.close()
    
    @staticmethod
    def delete_user(user_id: int, db: Session = None) -> bool:
        """
        Delete a user and all associated data
        
        Args:
            user_id: ID of the user to delete
            db: Database session (optional)
            
        Returns:
            True if successful, False otherwise
        """
        session = db or SessionLocal()
        try:
            user = session.query(User).filter(User.user_id == user_id).first()
            if not user:
                return False
            
            # Delete user (cascade will handle related data)
            session.delete(user)
            session.commit()
            return True
        except Exception as e:
            session.rollback()
            raise e
        finally:
            if not db:
                session.close()
    
    @staticmethod
    def get_user_stats(db: Session = None) -> Dict[str, Any]:
        """
        Get system-wide user statistics
        
        Args:
            db: Database session (optional)
            
        Returns:
            Dictionary with user statistics
        """
        session = db or SessionLocal()
        try:
            # Total users count
            total_users = session.query(User).count()
            
            # Recent users (last 30 days)
            from datetime import datetime, timedelta
            thirty_days_ago = datetime.utcnow() - timedelta(days=30)
            recent_users = session.query(User).filter(
                User.create_date >= thirty_days_ago
            ).count()
            
            # Users with apps
            users_with_apps = session.query(User).join(App).distinct().count()
            
            # Recent users list (last 10)
            recent_users_list = session.query(User).filter(
                User.create_date >= thirty_days_ago
            ).order_by(User.create_date.desc()).limit(10).all()
            
            recent_users_data = []
            for user in recent_users_list:
                recent_users_data.append({
                    'user_id': user.user_id,
                    'email': user.email,
                    'name': user.name,
                    'created_at': user.create_date.isoformat() if user.create_date else None
                })
            
            return {
                'total_users': total_users,
                'recent_users': recent_users,
                'users_with_apps': users_with_apps,
                'recent_users_list': recent_users_data
            }
        finally:
            if not db:
                session.close() 