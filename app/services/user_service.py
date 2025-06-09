from typing import List, Optional, Tuple, Dict, Any
from model.user import User
from model.app import App
from model.api_key import APIKey
from extensions import db
from sqlalchemy.orm import joinedload
from sqlalchemy import func, or_
from utils.logger import get_logger
from utils.error_handlers import (
    handle_database_errors, NotFoundError, ValidationError, 
    validate_required_fields, safe_execute
)
from utils.database import safe_db_execute

logger = get_logger(__name__)


class UserService:
    
    @staticmethod
    @handle_database_errors("get_all_users")
    def get_all_users(page: int = 1, per_page: int = 10) -> Tuple[List[User], int]:
        """
        Get all users with pagination
        
        Args:
            page: Page number (1-based)
            per_page: Number of users per page
            
        Returns:
            Tuple of (users_list, total_count)
        """
        if page < 1:
            page = 1
        if per_page < 1 or per_page > 100:  # Limit max per page
            per_page = 10
        
        def query_operation():
            users_query = db.session.query(User).options(
                joinedload(User.apps),
                joinedload(User.api_keys)
            )
            total = users_query.count()
            offset = (page - 1) * per_page
            users = users_query.offset(offset).limit(per_page).all()
            return users, total
        
        users, total = safe_db_execute(query_operation, "get_all_users")
        logger.info(f"Retrieved {len(users)} users (page {page}/{per_page}, total: {total})")
        return users, total
    
    @staticmethod
    @handle_database_errors("get_user_by_id")
    def get_user_by_id(user_id: int) -> Optional[User]:
        """
        Get user by ID with related data
        
        Args:
            user_id: ID of the user
            
        Returns:
            User instance or None if not found
        """
        if not user_id or user_id <= 0:
            return None
        
        def query_operation():
            return db.session.query(User).options(
                joinedload(User.apps),
                joinedload(User.api_keys)
            ).filter(User.user_id == user_id).first()
        
        user = safe_db_execute(query_operation, "get_user_by_id")
        if user:
            logger.debug(f"Retrieved user {user_id}: {user.email}")
        return user
    
    @staticmethod
    @handle_database_errors("get_user_by_email")
    def get_user_by_email(email: str) -> Optional[User]:
        """
        Get user by email
        
        Args:
            email: User's email address
            
        Returns:
            User instance or None if not found
        """
        if not email or not email.strip():
            return None
        
        email = email.strip().lower()
        
        def query_operation():
            return db.session.query(User).filter(User.email == email).first()
        
        user = safe_db_execute(query_operation, "get_user_by_email")
        if user:
            logger.debug(f"Retrieved user by email: {email}")
        return user
    
    @staticmethod
    @handle_database_errors("create_user")
    def create_user(user_data: dict) -> User:
        """
        Create a new user
        
        Args:
            user_data: Dictionary containing user information
            
        Returns:
            Created User instance
        """
        # Validate required fields
        required_fields = ['email']
        validate_required_fields(user_data, required_fields)
        
        # Clean and validate email
        email = user_data['email'].strip().lower()
        if not email:
            raise ValidationError("Email cannot be empty")
        
        # Check if user already exists
        existing_user = UserService.get_user_by_email(email)
        if existing_user:
            raise ValidationError(f"User with email {email} already exists")
        
        def create_operation():
            user = User(
                email=email,
                name=user_data.get('name', '').strip() or None
            )
            db.session.add(user)
            db.session.flush()  # Get the ID
            return user
        
        user = safe_db_execute(create_operation, "create_user")
        logger.info(f"Created new user: {user.email} (ID: {user.user_id})")
        return user
    
    @staticmethod
    @handle_database_errors("update_user")
    def update_user(user_id: int, user_data: dict) -> Optional[User]:
        """
        Update user information
        
        Args:
            user_id: ID of the user to update
            user_data: Dictionary containing updated user information
            
        Returns:
            Updated User instance or None if not found
        """
        user = UserService.get_user_by_id(user_id)
        if not user:
            raise NotFoundError(f"User with ID {user_id} not found", "user")
        
        def update_operation():
            # Only update allowed fields
            allowed_fields = ['name', 'email']
            updated_fields = []
            
            for key, value in user_data.items():
                if key in allowed_fields and hasattr(user, key):
                    if key == 'email' and value:
                        # Validate and clean email
                        new_email = value.strip().lower()
                        if new_email != user.email:
                            # Check if new email already exists
                            existing_user = UserService.get_user_by_email(new_email)
                            if existing_user and existing_user.user_id != user_id:
                                raise ValidationError(f"Email {new_email} is already in use")
                            setattr(user, key, new_email)
                            updated_fields.append(f"{key}: {new_email}")
                    elif key == 'name':
                        name = value.strip() if value else None
                        setattr(user, key, name)
                        updated_fields.append(f"{key}: {name}")
            
            db.session.flush()
            return user, updated_fields
        
        user, updated_fields = safe_db_execute(update_operation, "update_user")
        logger.info(f"Updated user {user_id}: {', '.join(updated_fields) if updated_fields else 'no changes'}")
        return user
    
    @staticmethod
    @handle_database_errors("delete_user")
    def delete_user(user_id: int) -> bool:
        """
        Delete user and all associated data (apps, API keys, etc.)
        
        Args:
            user_id: ID of the user to delete
            
        Returns:
            True if deletion was successful
        """
        user = UserService.get_user_by_id(user_id)
        if not user:
            raise NotFoundError(f"User with ID {user_id} not found", "user")
        
        user_email = user.email
        
        def delete_operation():
            # Count apps before deletion for logging
            apps_count = len(user.apps)
            app_ids = [app.app_id for app in user.apps] if apps_count > 0 else []
            
            # Delete all user's apps using AppService (this will cascade to all related entities)
            if apps_count > 0:
                # Import AppService here to avoid circular imports
                from services.app_service import AppService
                
                # Delete each app using AppService which handles proper cascading
                # This will also delete all associated API keys, agents, repositories, etc.
                for app in user.apps[:]:  # Use slice copy to avoid modification during iteration
                    AppService.delete_app(app.app_id)
                
                logger.info(f"Deleted {apps_count} apps (IDs: {app_ids}) for user {user_email}")
            
            # Finally delete the user
            db.session.delete(user)
            db.session.flush()
            
            return True
        
        result = safe_db_execute(delete_operation, "delete_user")
        logger.info(f"Successfully deleted user: {user_email} (ID: {user_id})")
        return result
    
    @staticmethod
    @handle_database_errors("get_user_stats")
    def get_user_stats() -> Dict[str, Any]:
        """
        Get user statistics for admin dashboard
        
        Returns:
            Dictionary containing user statistics
        """
        def stats_operation():
            # Total users count
            total_users = db.session.query(User).count()
            
            # Get recent users (last 10)
            recent_users = db.session.query(User).order_by(User.create_date.desc()).limit(10).all()
            
            # Get users with most apps
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
        
        stats = safe_db_execute(stats_operation, "get_user_stats")
        logger.info(f"Generated user stats: {stats['total_users']} total users")
        return stats
    
    @staticmethod
    @handle_database_errors("search_users")
    def search_users(query: str, page: int = 1, per_page: int = 10) -> Tuple[List[User], int]:
        """
        Search users by name or email
        
        Args:
            query: Search query string
            page: Page number (1-based)
            per_page: Number of users per page
            
        Returns:
            Tuple of (matching_users, total_count)
        """
        if not query or not query.strip():
            return UserService.get_all_users(page, per_page)
        
        if page < 1:
            page = 1
        if per_page < 1 or per_page > 100:
            per_page = 10
        
        query = query.strip()
        search_filter = f"%{query}%"
        
        def search_operation():
            users_query = db.session.query(User).filter(
                or_(
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
        
        users, total = safe_db_execute(search_operation, "search_users")
        logger.info(f"Search '{query}' returned {len(users)} users (page {page}/{per_page}, total: {total})")
        return users, total
    
    @staticmethod
    @handle_database_errors("get_user_basic")
    def get_user_basic(user_id: int) -> Optional[User]:
        """
        Get user by ID without loading relationships (lighter query)
        
        Args:
            user_id: ID of the user
            
        Returns:
            User instance or None if not found
        """
        if not user_id or user_id <= 0:
            return None
        
        def query_operation():
            return db.session.query(User).filter(User.user_id == user_id).first()
        
        user = safe_db_execute(query_operation, "get_user_basic")
        if user:
            logger.debug(f"Retrieved basic user info for {user_id}")
        return user
    
    @staticmethod
    @handle_database_errors("get_or_create_user")
    def get_or_create_user(email: str, name: str = None) -> Tuple[User, bool]:
        """
        Get existing user or create new one (useful for OAuth flows)
        
        Args:
            email: User's email address
            name: User's name (optional)
            
        Returns:
            Tuple of (User instance, was_created_boolean)
        """
        if not email or not email.strip():
            raise ValidationError("Email is required")
        
        email = email.strip().lower()
        
        # Try to get existing user first
        existing_user = UserService.get_user_by_email(email)
        if existing_user:
            return existing_user, False
        
        # Create new user
        user_data = {'email': email}
        if name and name.strip():
            user_data['name'] = name.strip()
        
        new_user = UserService.create_user(user_data)
        logger.info(f"Created new user during get_or_create: {email}")
        return new_user, True
    
    @staticmethod
    @handle_database_errors("user_exists")
    def user_exists(user_id: int) -> bool:
        """
        Check if a user exists
        
        Args:
            user_id: ID of the user to check
            
        Returns:
            True if user exists, False otherwise
        """
        if not user_id or user_id <= 0:
            return False
        
        def check_operation():
            return db.session.query(User.user_id).filter(User.user_id == user_id).first() is not None
        
        exists = safe_db_execute(check_operation, "user_exists")
        return exists
    
    @staticmethod
    @handle_database_errors("get_user_app_count")
    def get_user_app_count(user_id: int) -> int:
        """
        Get the number of apps owned by a user
        
        Args:
            user_id: ID of the user
            
        Returns:
            Number of apps owned by the user
        """
        if not user_id or user_id <= 0:
            return 0
        
        def count_operation():
            return db.session.query(App).filter(App.user_id == user_id).count()
        
        count = safe_db_execute(count_operation, "get_user_app_count")
        logger.debug(f"User {user_id} has {count} apps")
        return count
    
    @staticmethod
    def validate_user_data(user_data: dict) -> dict:
        """
        Validate and clean user data
        
        Args:
            user_data: Raw user data dictionary
            
        Returns:
            Cleaned and validated user data
        """
        if not isinstance(user_data, dict):
            raise ValidationError("User data must be a dictionary")
        
        cleaned_data = {}
        
        # Email validation
        if 'email' in user_data:
            email = user_data['email']
            if email:
                email = str(email).strip().lower()
                if not email:
                    raise ValidationError("Email cannot be empty")
                # Basic email format validation
                if '@' not in email or '.' not in email:
                    raise ValidationError("Invalid email format")
                cleaned_data['email'] = email
        
        # Name validation  
        if 'name' in user_data:
            name = user_data['name']
            if name:
                name = str(name).strip()
                if len(name) > 255:
                    raise ValidationError("Name cannot exceed 255 characters")
                cleaned_data['name'] = name or None
        
        return cleaned_data 