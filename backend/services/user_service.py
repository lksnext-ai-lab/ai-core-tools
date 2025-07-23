from sqlalchemy.orm import Session
from models.user import User
from db.session import SessionLocal
from typing import Tuple

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