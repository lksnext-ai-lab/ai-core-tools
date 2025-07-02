from extensions import db
from model.resource import Resource
from typing import List
import os
from services.silo_service import SiloService
from werkzeug.datastructures import FileStorage
from utils.logger import get_logger

REPO_BASE_FOLDER = os.path.abspath(os.getenv('REPO_BASE_FOLDER'))
logger = get_logger(__name__)

class ResourceService:

    # Supported file extensions
    SUPPORTED_EXTENSIONS = {'.pdf', '.docx', '.txt'}

    @staticmethod
    def get_resources_by_repo_id(repository_id: int) -> List[Resource]:
        return db.session.query(Resource).filter(Resource.repository_id == repository_id).all() 
    
    @staticmethod
    def create_resource_from_file(file: FileStorage, name: str, repository_id: int) -> Resource:
        """
        Create a resource from an uploaded file
        
        Args:
            file: The uploaded file
            name: The name for the resource
            repository_id: The ID of the repository
            
        Returns:
            The created Resource instance
            
        Raises:
            ValueError: If file is invalid or missing
        """
        if not file or file.filename == '':
            raise ValueError("No file provided or filename is empty")
        
        # Create repository directory if it doesn't exist
        repository_path = os.path.join(REPO_BASE_FOLDER, str(repository_id))
        os.makedirs(repository_path, exist_ok=True)
        
        # Create the resource object
        resource = Resource(name=name, uri=file.filename, repository_id=repository_id)
        
        # Save file to disk
        file_path = os.path.join(repository_path, file.filename)
        file.save(file_path)
        
        # Save to database
        db.session.add(resource)
        db.session.commit()
        db.session.refresh(resource)
        
        # Index in silo
        try:
            SiloService.index_resource(resource)
            logger.info(f"Resource {resource.resource_id} indexed successfully in silo")
        except Exception as e:
            logger.error(f"Failed to index resource {resource.resource_id} in silo: {str(e)}")
            # Note: We don't rollback here as the file and database record are already created
            # The indexing can be retried later
        
        return resource
    
    @staticmethod
    def create_resource(file, name: str, resource: Resource) -> Resource:
        """
        Legacy method - kept for backward compatibility
        """
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
    def delete_resource(resource_id: int) -> bool:
        """
        Delete a resource completely (file, database record, and silo indexing)
        
        Args:
            resource_id: The ID of the resource to delete
            
        Returns:
            True if deletion was successful, False if resource not found
        """
        resource = db.session.query(Resource).filter(Resource.resource_id == resource_id).first()
        if not resource:
            logger.warning(f"Resource {resource_id} not found for deletion")
            return False
        
        try:
            # Delete from silo first
            SiloService.delete_resource(resource)
            logger.info(f"Resource {resource_id} deleted from silo")
            
            # Delete file from disk
            file_path = os.path.join(REPO_BASE_FOLDER, str(resource.repository_id), resource.uri)
            if os.path.exists(file_path):
                os.remove(file_path)
                logger.info(f"File {file_path} deleted from disk")
            
            # Delete from database
            db.session.delete(resource)
            db.session.commit()
            logger.info(f"Resource {resource_id} deleted from database")
            
            return True
            
        except Exception as e:
            logger.error(f"Error deleting resource {resource_id}: {str(e)}")
            db.session.rollback()
            return False
    
    @staticmethod
    def get_resource(resource_id: int) -> Resource:
        """
        Get a resource by its ID
        
        Args:
            resource_id: The ID of the resource
            
        Returns:
            The Resource instance or None if not found
        """
        return db.session.query(Resource).filter(Resource.resource_id == resource_id).first()
    
    @staticmethod
    def get_resource_file_path(resource_id: int) -> str:
        """
        Get the file path for a resource
        
        Args:
            resource_id: The ID of the resource
            
        Returns:
            The full file path or None if resource not found
        """
        resource = ResourceService.get_resource(resource_id)
        if not resource:
            return None
        
        return os.path.join(REPO_BASE_FOLDER, str(resource.repository_id), resource.uri)
