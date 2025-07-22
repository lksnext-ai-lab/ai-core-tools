from models.repository import Repository
from models.resource import Resource
from models.output_parser import OutputParser
from db.session import SessionLocal
from typing import Optional, List
import os
import shutil
from dotenv import load_dotenv
from services.silo_service import SiloService
from models.silo import SiloType
from services.output_parser_service import OutputParserService

load_dotenv()
REPO_BASE_FOLDER = os.path.abspath(os.getenv("REPO_BASE_FOLDER"))

class RepositoryService:

    @staticmethod
    def get_repository(repository_id: int) -> Optional[Repository]:
        session = SessionLocal()
        try:
            return session.query(Repository).filter(Repository.repository_id == repository_id).first()
        finally:
            session.close()
    
    @staticmethod
    def get_repositories_by_app_id(app_id: int) -> List[Repository]:
        session = SessionLocal()
        try:
            return session.query(Repository).filter(Repository.app_id == app_id).all()
        finally:
            session.close()
    
    @staticmethod
    def create_repository(repository: Repository, embedding_service_id: Optional[int] = None) -> Repository:
        session = SessionLocal()
        try:
            silo_service = SiloService()
            silo_data = {
                'silo_id': 0,
                'name': 'silo for repository ' + repository.name,
                'description': 'silo for repository ' + repository.name,
                'status': 'active',
                'app_id': repository.app_id,
                'fixed_metadata': False,
                'embedding_service_id': embedding_service_id
            }
            silo = silo_service.create_or_update_silo(silo_data, SiloType.REPO)
            repository.silo_id = silo.silo_id
            output_parser_service = OutputParserService()
            repo_filter = output_parser_service.create_default_filter_for_repo(repository)
            silo.metadata_definition_id = repo_filter.parser_id
            session.add(repository)
            session.commit()
            session.refresh(repository)
            repo_folder = os.path.join(REPO_BASE_FOLDER, str(repository.repository_id))
            os.makedirs(repo_folder, exist_ok=True)
            
            return repository
        finally:
            session.close()
    
    @staticmethod
    def update_repository(repository: Repository, embedding_service_id: Optional[int] = None) -> Repository:
        session = SessionLocal()
        try:
            if repository.silo and embedding_service_id:
                repository.silo.embedding_service_id = embedding_service_id
            session.commit()
            return repository
        finally:
            session.close()
    
    @staticmethod
    def delete_repository(repository: Repository):
        if not repository:
            return
        
        session = SessionLocal()
        try:
            # Get silo and parser info before deletion
            silo = repository.silo
            parser_id = silo.metadata_definition_id if silo else None
            
            # Delete all resources first
            resources = session.query(Resource).filter(Resource.repository_id == repository.repository_id).all()
            for resource in resources:
                # Delete the physical file if exists
                file_path = os.path.join(REPO_BASE_FOLDER, str(repository.repository_id), resource.uri)
                if os.path.exists(file_path):
                    try:
                        os.remove(file_path)
                    except OSError:
                        pass  # Ignore errors if file cannot be deleted
            
            # Delete all resource records
            session.query(Resource).filter(Resource.repository_id == repository.repository_id).delete()
            
            # Delete repository folder if exists
            repo_folder = os.path.join(REPO_BASE_FOLDER, str(repository.repository_id))
            if os.path.exists(repo_folder):
                try:
                    shutil.rmtree(repo_folder)
                except OSError:
                    pass  # Ignore errors if folder cannot be deleted
                
            # Delete vector collection and silo
            if silo:
                SiloService.delete_collection(silo.silo_id)
                session.delete(silo)
                
            # Delete repository
            session.delete(repository)
            
            # Delete output parser if exists
            if parser_id:
                session.query(OutputParser).filter_by(parser_id=parser_id).delete()
            
            session.commit()
        finally:
            session.close() 