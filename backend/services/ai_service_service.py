from db.session import SessionLocal
from models.ai_service import AIService

class AIServiceService:
    
    @staticmethod
    def delete_by_app_id(app_id: int):
        """Delete all AI services for a specific app"""
        session = SessionLocal()
        try:
            session.query(AIService).filter(AIService.app_id == app_id).delete()
            session.commit()
        finally:
            session.close() 