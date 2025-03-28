from extensions import db
from model.resource import Resource
from typing import List
import os
from services.silo_service import SiloService
REPO_BASE_FOLDER = os.getenv('REPO_BASE_FOLDER')
class ResourceService:

    @staticmethod
    def get_resources_by_repo_id(repository_id: int) -> List[Resource]:
        return db.session.query(Resource).filter(Resource.repository_id == repository_id).all() 
    
    @staticmethod
    def create_resource(file, name: str, resource: Resource) -> Resource:
        file.save(os.path.join(REPO_BASE_FOLDER, str(resource.repository_id), file.filename))
        
        db.session.add(resource)
        db.session.commit()
        db.session.refresh(resource)
        
        SiloService.index_resource(resource)
        return resource
    
    @staticmethod
    def delete_resource(resource_id: int):
        resource = db.session.query(Resource).filter(Resource.resource_id == resource_id).first()
        SiloService.delete_resource(resource)
        os.remove(os.path.join(REPO_BASE_FOLDER, str(resource.repository_id), resource.uri))
        db.session.delete(resource)
        db.session.commit()
