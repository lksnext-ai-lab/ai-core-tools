from typing import Optional, List
from sqlalchemy.orm import Session
from sqlalchemy import text
from models.silo import Silo
from models.output_parser import OutputParser
from models.embedding_service import EmbeddingService
from utils.logger import get_logger
from repositories.output_parser_repository import OutputParserRepository
from repositories.embedding_service_repository import EmbeddingServiceRepository

logger = get_logger(__name__)


class SiloRepository:
    """Repository class for Silo database operations"""
    
    @staticmethod
    def get_by_id(silo_id: int, db: Session) -> Optional[Silo]:
        """
        Retrieve a silo by its ID
        """
        return db.query(Silo).filter(Silo.silo_id == silo_id).first()
    
    @staticmethod
    def get_by_app_id(app_id: int, db: Session) -> List[Silo]:
        """
        Retrieve all silos by app_id
        """
        return db.query(Silo).filter(Silo.app_id == app_id).all()
    
    @staticmethod
    def create(silo: Silo, db: Session) -> Silo:
        """
        Create a new silo
        """
        db.add(silo)
        db.commit()
        db.refresh(silo)
        return silo
    
    @staticmethod
    def update(silo: Silo, db: Session) -> Silo:
        """
        Update an existing silo
        """
        db.add(silo)
        db.commit()
        db.refresh(silo)
        return silo
    
    @staticmethod
    def delete(silo_id: int, db: Session) -> bool:
        """
        Delete a silo by its ID
        """
        silo = db.query(Silo).filter(Silo.silo_id == silo_id).first()
        if not silo:
            return False
        db.delete(silo)
        db.commit()
        return True
    
    @staticmethod
    def get_output_parsers_by_app_id(app_id: int, db: Session) -> List[OutputParser]:
        """
        Get all output parsers for a specific app (using existing repository)
        """
        parser_repo = OutputParserRepository()
        return parser_repo.get_by_app_id(db, app_id)
    
    @staticmethod
    def get_embedding_services_by_app_id(app_id: int, db: Session) -> List[EmbeddingService]:
        """
        Get all embedding services for a specific app (using existing repository)
        """
        return EmbeddingServiceRepository.get_by_app_id(db, app_id)
    
    @staticmethod
    def get_output_parser_by_id(parser_id: int, db: Session) -> Optional[OutputParser]:
        """
        Get an output parser by its ID (using existing repository)
        """
        parser_repo = OutputParserRepository()
        return parser_repo.get_by_id(db, parser_id)
    
    # ==================== COLLECTION QUERIES ====================
    
    @staticmethod
    def check_collection_exists(silo_id: int, db: Session) -> bool:
        """
        Check if a silo collection exists in the vector database
        """
        sql = text("SELECT COUNT(*) FROM langchain_pg_collection WHERE name = :silo_id;")
        result = db.execute(sql, {'silo_id': 'silo_' + str(silo_id)})
        return result.fetchone()[0] > 0
    
    @staticmethod
    def get_collection_uuid(silo_id: int, db: Session) -> str:
        """
        Get the UUID of a silo collection
        """
        sql = text("SELECT uuid FROM langchain_pg_collection WHERE name = :silo_id;")
        result = db.execute(sql, {'silo_id': 'silo_' + str(silo_id)})
        return result.fetchone()[0]
    
    @staticmethod
    def count_documents_in_collection(collection_uuid: str, db: Session) -> int:
        """
        Count documents in a collection by UUID
        """
        sql = text("SELECT COUNT(*) FROM langchain_pg_embedding WHERE collection_id = :collection_uuid;")
        result = db.execute(sql, {'collection_uuid': collection_uuid})
        return result.fetchone()[0]
    
    @staticmethod
    def get_embedding_service_by_id(service_id: int, db: Session) -> Optional[EmbeddingService]:
        """
        Get an embedding service by its ID (using existing repository)
        """
        return EmbeddingServiceRepository.get_by_id(db, service_id)
    
    @staticmethod
    def get_form_data_for_silo(app_id: int, silo_id: int, db: Session) -> dict:
        """
        Get form data needed for silo editing (consolidating multiple queries)
        """
        output_parsers = SiloRepository.get_output_parsers_by_app_id(app_id, db)
        silo = SiloRepository.get_by_id(silo_id, db) if silo_id != 0 else None
        embedding_services = SiloRepository.get_embedding_services_by_app_id(app_id, db)
        
        return {
            'output_parsers': output_parsers,
            'silo': silo,
            'embedding_services': embedding_services
        }
