from db.session import SessionLocal
from models.resource import Resource
from typing import List, Tuple, Optional
import os
from services.silo_service import SiloService
from utils.logger import get_logger

REPO_BASE_FOLDER = os.path.abspath(os.getenv('REPO_BASE_FOLDER'))
logger = get_logger(__name__)

class ResourceService:

    # Supported file extensions
    SUPPORTED_EXTENSIONS = {'.pdf', '.docx', '.txt'}

    @staticmethod
    def get_resources_by_repo_id(repository_id: int) -> List[Resource]:
        session = SessionLocal()
        try:
            return session.query(Resource).filter(Resource.repository_id == repository_id).all()
        finally:
            session.close()
    
    @staticmethod
    def delete_resource(resource_id: int) -> bool:
        """
        Delete a resource completely (file, database record, and silo indexing)
        
        Args:
            resource_id: The ID of the resource to delete
            
        Returns:
            True if deletion was successful, False if resource not found
        """
        session = SessionLocal()
        try:
            resource = session.query(Resource).filter(Resource.resource_id == resource_id).first()
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
                session.delete(resource)
                session.commit()
                logger.info(f"Resource {resource_id} deleted from database")
                
                return True
                
            except Exception as e:
                logger.error(f"Error deleting resource {resource_id}: {str(e)}")
                session.rollback()
                return False
        finally:
            session.close()
    
    @staticmethod
    def get_resource(resource_id: int) -> Resource:
        """
        Get a resource by its ID
        
        Args:
            resource_id: The ID of the resource
            
        Returns:
            The Resource instance or None if not found
        """
        session = SessionLocal()
        try:
            return session.query(Resource).filter(Resource.resource_id == resource_id).first()
        finally:
            session.close()
    
    @staticmethod
    def get_resource_file_path(resource_id: int) -> Optional[str]:
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
    
    @staticmethod
    def create_multiple_resources(files: List, repository_id: int, custom_names: dict = None) -> Tuple[List[Resource], List[dict]]:
        """
        Create multiple resources from uploaded files
        
        Args:
            files: List of uploaded files
            repository_id: The ID of the repository
            custom_names: Dictionary mapping file indices to custom names (without extensions)
            
        Returns:
            Tuple containing a list of created Resource instances and a list of failed files
            
        Raises:
            ValueError: If any file is invalid or missing
        """
        if not files:
            raise ValueError("No files provided")
        
        if custom_names is None:
            custom_names = {}
        
        repository_path = os.path.join(REPO_BASE_FOLDER, str(repository_id))
        os.makedirs(repository_path, exist_ok=True)

        created_resources = []
        failed_files = []
        
        session = SessionLocal()
        try:
            for index, file in enumerate(files):
                custom_name = custom_names.get(index)
                result = ResourceService._process_single_file(file, repository_id, repository_path, custom_name, session)
                if isinstance(result, Resource):
                    created_resources.append(result)
                    logger.info(f"Resource {result.name} prepared for indexing")
                else:
                    failed_files.append(result)

            if created_resources:
                try:
                    session.commit()
                    logger.info(f"Successfully saved {len(created_resources)} resources to database")
                    ResourceService._index_resources(created_resources)
                except Exception as e:
                    logger.error(f"Error committing resources to database: {str(e)}")
                    session.rollback()
                    ResourceService._cleanup_files(created_resources, repository_path)
                    raise

            if failed_files:
                logger.warning(f"Failed to process {len(failed_files)} files: {failed_files}")

            return created_resources, failed_files
        finally:
            session.close()

    @staticmethod
    def _process_single_file(file, repository_id: int, repository_path: str, custom_name: str = None, session=None):
        """
        Process a single file upload
        
        Args:
            file: The uploaded file
            repository_id: The ID of the repository
            repository_path: The path to save the file
            custom_name: Custom name for the resource (without extension)
            session: Database session to use
            
        Returns:
            Resource instance if successful, error dict if failed
        """
        if not file or not hasattr(file, 'filename') or file.filename == '':
            return {'filename': 'Unknown', 'error': 'Empty filename'}
            
        file_extension = os.path.splitext(file.filename)[1].lower()
        if file_extension not in ResourceService.SUPPORTED_EXTENSIONS:
            supported = ', '.join(ResourceService.SUPPORTED_EXTENSIONS)
            return {
                'filename': file.filename,
                'error': f"Unsupported file type: {file_extension}. Supported: {supported}"
            }
        
        # Use custom name if provided, otherwise use original filename without extension
        if custom_name and custom_name.strip():
            name = custom_name.strip()
            # Ensure the saved filename includes the custom name with original extension
            save_filename = f"{name}{file_extension}"
        else:
            name = os.path.splitext(file.filename)[0]
            save_filename = file.filename
        
        try:
            resource = Resource(
                name=name, 
                uri=save_filename, 
                repository_id=repository_id,
                type=file_extension  # Set the file type based on extension
            )
            file_path = os.path.join(repository_path, save_filename)
            
            # Save the file with the new name
            if hasattr(file, 'save'):
                file.save(file_path)
            else:
                # For FastAPI UploadFile - read content properly
                if hasattr(file, 'file'):
                    # Reset file position to beginning
                    file.file.seek(0)
                    content = file.file.read()
                else:
                    content = file.read()
                
                with open(file_path, 'wb') as f:
                    f.write(content)
            
            session.add(resource)
            session.flush()
            return resource
            
        except Exception as e:
            logger.error(f"Error processing file {file.filename}: {str(e)}")
            return {'filename': file.filename, 'error': str(e)}

    @staticmethod
    def _index_resources(resources: List[Resource]):
        indexed_count = 0
        for resource in resources:
            try:
                SiloService.index_resource(resource)
                indexed_count += 1
            except Exception as e:
                logger.error(f"Failed to index resource {resource.resource_id}: {str(e)}")
        logger.info(f"Successfully indexed {indexed_count}/{len(resources)} resources")

    @staticmethod
    def _cleanup_files(resources: List[Resource], repository_path: str):
        for resource in resources:
            file_path = os.path.join(repository_path, resource.uri)
            if os.path.exists(file_path):
                try:
                    os.remove(file_path)
                except Exception:
                    pass 