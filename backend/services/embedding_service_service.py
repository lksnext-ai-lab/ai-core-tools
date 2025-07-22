from models.embedding_service import EmbeddingService
from db.session import SessionLocal

class EmbeddingServiceService:

    @staticmethod
    def get_embedding_services_by_app_id(app_id):
        session = SessionLocal()
        try:
            return session.query(EmbeddingService).filter(EmbeddingService.app_id == app_id).all()
        finally:
            session.close()

    @staticmethod
    def get_embedding_services():
        session = SessionLocal()
        try:
            return session.query(EmbeddingService).all()
        finally:
            session.close()
    
    @staticmethod
    def get_embedding_service(embedding_service_id):
        session = SessionLocal()
        try:
            return session.query(EmbeddingService).filter(EmbeddingService.service_id == embedding_service_id).first()
        finally:
            session.close()
    
    @staticmethod
    def create_embedding_service(embedding_service):
        session = SessionLocal()
        try:
            session.add(embedding_service)
            session.commit()
        finally:
            session.close()

    @staticmethod
    def delete_embedding_service(embedding_service_id):
        session = SessionLocal()
        try:
            embedding_service = session.query(EmbeddingService).filter(EmbeddingService.service_id == embedding_service_id).first()
            if embedding_service:
                session.delete(embedding_service)
                session.commit()
        finally:
            session.close()

    @staticmethod
    def delete_by_app_id(app_id):
        session = SessionLocal()
        try:
            embedding_services = session.query(EmbeddingService).filter(EmbeddingService.app_id == app_id).all()
            for embedding_service in embedding_services:
                session.delete(embedding_service)
            session.commit()
        finally:
            session.close() 