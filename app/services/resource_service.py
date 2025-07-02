from extensions import db
from model.resource import Resource
from typing import List
import os
from services.silo_service import SiloService
from utils.logger import get_logger

logger = get_logger(__name__)
REPO_BASE_FOLDER = os.getenv('REPO_BASE_FOLDER')

class ResourceService:

    # Supported file extensions
    SUPPORTED_EXTENSIONS = {'.pdf', '.docx', '.txt'}

    @staticmethod
    def get_resources_by_repo_id(repository_id: int) -> List[Resource]:
        return db.session.query(Resource).filter(Resource.repository_id == repository_id).all() 
    
    @staticmethod
    def create_resource(file, name: str, resource: Resource) -> Resource:
        # Validate file extension
        file_extension = os.path.splitext(file.filename)[1].lower()
        if file_extension not in ResourceService.SUPPORTED_EXTENSIONS:
            supported = ', '.join(ResourceService.SUPPORTED_EXTENSIONS)
            raise ValueError(f"Unsupported file type: {file_extension}. Supported types: {supported}")
        
        # Save file
        file_path = os.path.join(REPO_BASE_FOLDER, str(resource.repository_id), file.filename)
        file.save(file_path)
        
        db.session.add(resource)
        db.session.commit()
        db.session.refresh(resource)
        
        # Index the resource
        try:
            SiloService.index_resource(resource)
            logger.info(f"Successfully indexed resource {resource.resource_id} with type {file_extension}")
        except Exception as e:
            logger.error(f"Failed to index resource {resource.resource_id}: {str(e)}")
            # Consider whether to rollback the resource creation or continue
            
        return resource
    
    @staticmethod
    def delete_resource(resource_id: int):
        resource = db.session.query(Resource).filter(Resource.resource_id == resource_id).first()
        SiloService.delete_resource(resource)
        os.remove(os.path.join(REPO_BASE_FOLDER, str(resource.repository_id), resource.uri))
        db.session.delete(resource)
        db.session.commit()
