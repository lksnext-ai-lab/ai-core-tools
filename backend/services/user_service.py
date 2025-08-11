from sqlalchemy.orm import Session
from models.user import User
from repositories.user_repository import UserRepository
from typing import Tuple, List, Dict, Any

class UserService:
    
    @staticmethod
    def get_or_create_user(db: Session, email: str, name: str = None) -> Tuple[User, bool]:
        """
        Get existing user or create new user if doesn't exist.
        Returns: (user, created) where created is True if user was just created
        """
        user_repo = UserRepository(db)
        
        # Try to find existing user
        user = user_repo.get_by_email(email)
        
        if user:
            # User exists, update name if provided and different
            user = user_repo.update(user, name)
            return user, False
        
        # Create new user
        new_user = user_repo.create(email, name)
        return new_user, True
    
    @staticmethod
    def get_user_by_id(db: Session, user_id: int) -> User:
        """Get user by ID"""
        user_repo = UserRepository(db)
        return user_repo.get_by_id(user_id)
    
    @staticmethod
    def get_user_by_email(db: Session, email: str) -> User:
        """Get user by email"""
        user_repo = UserRepository(db)
        return user_repo.get_by_email(email)
    
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
    def get_all_users(db: Session, page: int = 1, per_page: int = 10) -> Tuple[List[Dict], int]:
        """
        Get all users with pagination
        
        Args:
            db: Database session
            page: Page number (1-based)
            per_page: Number of users per page
            
        Returns:
            Tuple of (users_list, total_count)
        """
        user_repo = UserRepository(db)
        users, total = user_repo.get_all_paginated(page, per_page)
        
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
    
    @staticmethod
    def get_user_by_id_with_relations(db: Session, user_id: int) -> User:
        """
        Get user by ID with related data
        
        Args:
            db: Database session
            user_id: ID of the user
            
        Returns:
            User instance or None if not found
        """
        user_repo = UserRepository(db)
        return user_repo.get_by_id_with_relations(user_id)
    
    @staticmethod
    def search_users(db: Session, query: str, page: int = 1, per_page: int = 10) -> Tuple[List[Dict], int]:
        """
        Search users by name or email
        
        Args:
            db: Database session
            query: Search query
            page: Page number (1-based)
            per_page: Number of users per page
            
        Returns:
            Tuple of (users_list, total_count)
        """
        user_repo = UserRepository(db)
        users, total = user_repo.search_users(query, page, per_page)
        
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
    
    @staticmethod
    def delete_user(db: Session, user_id: int) -> bool:
        """
        Delete a user and all associated data
        
        Args:
            db: Database session
            user_id: ID of the user to delete
            
        Returns:
            True if successful, False otherwise
        """
        user_repo = UserRepository(db)
        return user_repo.delete(user_id)
    
    @staticmethod
    def get_user_stats(db: Session) -> Dict[str, Any]:
        """
        Get system-wide user statistics
        
        Args:
            db: Database session
            
        Returns:
            Dictionary with user statistics
        """
        user_repo = UserRepository(db)
        
        # Total users count
        total_users = user_repo.get_total_count()
        
        # Recent users (last 30 days)
        recent_users = user_repo.get_recent_users_count(30)
        
        # Users with apps
        users_with_apps = user_repo.get_users_with_apps_count()
        
        # Recent users list (last 10)
        recent_users_list = user_repo.get_recent_users_list(30, 10)
        
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