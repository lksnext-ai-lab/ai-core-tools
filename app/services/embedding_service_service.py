from model.embedding_service import EmbeddingService
from extensions import db

class EmbeddingServiceService:

    @staticmethod
    def get_embedding_services_by_app_id(app_id):
        return db.session.query(EmbeddingService).filter(EmbeddingService.app_id == app_id).all()

    @staticmethod
    def get_embedding_services():
        return db.session.query(EmbeddingService).all()
    
    @staticmethod
    def get_embedding_service( embedding_service_id):
        return db.session.query(EmbeddingService).filter(EmbeddingService.embedding_service_id == embedding_service_id).first()
    
    @staticmethod
    def create_embedding_service(embedding_service):
        db.session.add(embedding_service)