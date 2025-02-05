from app.model.repository import Repository
from app.model.resource import Resource
from app.extensions import db
from typing import Optional, List
from app.services.silo_service import SiloService
class RepositoryService:

    @staticmethod
    def get_repository(repository_id: int) -> Optional[Repository]:
            return db.session.query(Repository).filter(Repository.repository_id == repository_id).first()
    
    @staticmethod
    def get_repositories_by_app_id(app_id: int) -> List[Repository]:
        return db.session.query(Repository).filter(Repository.app_id == app_id).all()
    
    @staticmethod
    def create_repository(repository: Repository) -> Repository:
        db.session.add(repository)
        db.session.commit()
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
