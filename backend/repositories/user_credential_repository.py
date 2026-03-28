from typing import Optional
from sqlalchemy.orm import Session
from models.user_credential import UserCredential
from datetime import datetime
from utils.logger import get_logger

logger = get_logger(__name__)


class UserCredentialRepository:

    def __init__(self, db: Session):
        self.db = db

    def create(self, user_id: int, hashed_password: str) -> UserCredential:
        """Create a new credential record for a user."""
        cred = UserCredential(
            user_id=user_id,
            hashed_password=hashed_password,
            is_verified=False,
        )
        self.db.add(cred)
        self.db.flush()
        return cred

    def get_by_user_id(self, user_id: int) -> Optional[UserCredential]:
        return self.db.query(UserCredential).filter(UserCredential.user_id == user_id).first()

    def set_verification_token(self, user_id: int, token: str, expiry: datetime) -> Optional[UserCredential]:
        cred = self.get_by_user_id(user_id)
        if not cred:
            return None
        cred.verification_token = token
        cred.verification_token_expiry = expiry
        cred.updated_at = datetime.utcnow()
        self.db.flush()
        return cred

    def mark_verified(self, user_id: int) -> Optional[UserCredential]:
        cred = self.get_by_user_id(user_id)
        if not cred:
            return None
        cred.is_verified = True
        cred.verification_token = None
        cred.verification_token_expiry = None
        cred.updated_at = datetime.utcnow()
        self.db.flush()
        return cred

    def set_reset_token(self, user_id: int, token: str, expiry: datetime) -> Optional[UserCredential]:
        cred = self.get_by_user_id(user_id)
        if not cred:
            return None
        cred.reset_token = token
        cred.reset_token_expiry = expiry
        cred.updated_at = datetime.utcnow()
        self.db.flush()
        return cred

    def update_password(self, user_id: int, hashed_password: str) -> Optional[UserCredential]:
        cred = self.get_by_user_id(user_id)
        if not cred:
            return None
        cred.hashed_password = hashed_password
        cred.reset_token = None
        cred.reset_token_expiry = None
        cred.updated_at = datetime.utcnow()
        self.db.flush()
        return cred
