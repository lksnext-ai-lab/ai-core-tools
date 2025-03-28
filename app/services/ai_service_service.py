from extensions import db
from model.ai_service import AIService

class AIServiceService:
    
    @staticmethod
    def delete_by_app_id(app_id: int):
        """Delete all AI services for a specific app"""
        db.session.query(AIService).filter(AIService.app_id == app_id).delete()
        db.session.commit()
