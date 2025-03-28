from extensions import db
from model.api_key import APIKey

class APIKeyService:
    
    @staticmethod
    def delete_by_app_id(app_id: int):
        """Delete all API keys for a specific app"""
        db.session.query(APIKey).filter(APIKey.app_id == app_id).delete()
        db.session.commit()
