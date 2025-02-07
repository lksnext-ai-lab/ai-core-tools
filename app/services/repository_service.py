from app.model.repository import Repository
from app.model.resource import Resource
from app.extensions import db
from typing import Optional, List
from app.services.silo_service import SiloService
from app.model.silo import SiloType
from app.services.output_parser_service import OutputParserService
import os

REPO_BASE_FOLDER = os.getenv("REPO_BASE_FOLDER")

class RepositoryService:

    @staticmethod
    def get_repository(repository_id: int) -> Optional[Repository]:
            return db.session.query(Repository).filter(Repository.repository_id == repository_id).first()
    
    @staticmethod
    def get_repositories_by_app_id(app_id: int) -> List[Repository]:
        return db.session.query(Repository).filter(Repository.app_id == app_id).all()
    
    @staticmethod
    def create_repository(repository: Repository) -> Repository:
     
        silo_service = SiloService()
        silo_data = {
            'silo_id': 0,
            'name': 'silo for repository ' + repository.name,
            'description': 'silo for repository ' + repository.name,
            'status': 'active',
            'app_id': repository.app_id,
            'fixed_metadata': False
        }
        silo = silo_service.create_or_update_silo(silo_data, SiloType.REPO)
        repository.silo_id = silo.silo_id
        output_parser_service = OutputParserService()
        filter = output_parser_service.create_default_filter_for_repo(repository)
        silo.metadata_definition_id = filter.parser_id
        db.session.add(repository)
        db.session.commit()
        db.session.refresh(repository)

        repo_folder = os.path.join(REPO_BASE_FOLDER, str(repository.repository_id))
        os.makedirs(repo_folder, exist_ok=True)
        
        return repository
    
    @staticmethod   
    def update_repository(repository: Repository) -> Repository:
        db.session.commit()
        return repository
    
    @staticmethod
    def delete_repository(repository: Repository):
        silo = repository.silo
        db.session.query(Resource).filter(Resource.repository_id == repository.repository_id).delete()
        db.session.delete(repository)
        SiloService.delete_silo(silo.silo_id)
        db.session.commit()
