from models.resource import Resource
from repositories.resource_repository import ResourceRepository
from services.folder_service import FolderService
from typing import List, Tuple, Optional
import os
from services.silo_service import SiloService
from utils.logger import get_logger
from sqlalchemy.orm import Session
from fastapi import HTTPException, status, UploadFile

REPO_BASE_FOLDER = os.path.abspath(os.getenv('REPO_BASE_FOLDER'))
logger = get_logger(__name__)

class ResourceService:

    # Supported file extensions
    SUPPORTED_EXTENSIONS = {'.pdf', '.docx', '.txt'}


    @staticmethod
    def get_resources_by_repo_id(repository_id: int, db: Session) -> List[Resource]:
        """
        Get all resources by repository ID
        
        Args:
            repository_id: Repository ID
            db: Database session
            
        Returns:
            List of Resource instances
        """
        return ResourceRepository.get_by_repository_id(db, repository_id)
    
    @staticmethod
    def get_resource(resource_id: int, db: Session) -> Optional[Resource]:
        """
        Get a resource by its ID
        
        Args:
            resource_id: The ID of the resource
            db: Database session
            
        Returns:
            The Resource instance or None if not found
        """
        return ResourceRepository.get_by_id(db, resource_id)
    
    @staticmethod
    def move_resource_to_folder(resource_id: int, repository_id: int, new_folder_id: Optional[int], db: Session) -> dict:
        """
        Move a resource to a different folder within the same repository.
        Updates file system location, database record, and re-indexes in vector DB.
        
        Args:
            resource_id: ID of the resource to move
            repository_id: Repository ID (for validation)
            new_folder_id: New folder ID (None for root)
            db: Database session
            
        Returns:
            dict: Result with success status and updated resource info
        """
        try:
            # Get the resource
            resource = ResourceService.get_resource(resource_id, db)
            if not resource:
                raise ValueError(f"Resource {resource_id} not found")
            
            # Validate repository ownership
            if resource.repository_id != repository_id:
                raise ValueError(f"Resource {resource_id} does not belong to repository {repository_id}")
            
            # Validate new folder if provided
            if new_folder_id is not None:
                if not FolderService.validate_folder_access(new_folder_id, repository_id, db):
                    raise ValueError(f"Folder {new_folder_id} does not belong to repository {repository_id}")
            
            # Get old and new paths
            old_path = ResourceService.get_resource_file_path(resource_id, db)
            if not old_path:
                raise ValueError(f"Could not determine current path for resource {resource_id}")
            
            # Build new path
            repository_path = os.path.join(REPO_BASE_FOLDER, str(repository_id))
            if new_folder_id:
                folder_path = FolderService.get_folder_path(new_folder_id, db)
                new_path = os.path.join(repository_path, folder_path, resource.uri)
            else:
                new_path = os.path.join(repository_path, resource.uri)
            
            # Create target directory if it doesn't exist
            os.makedirs(os.path.dirname(new_path), exist_ok=True)
            
            # Move the file in the file system
            import shutil
            shutil.move(old_path, new_path)
            logger.info(f"Moved file from {old_path} to {new_path}")
            
            # Update database record
            resource.folder_id = new_folder_id
            db.add(resource)
            db.commit()  # Commit the database changes first
            logger.info(f"Updated resource {resource_id} folder_id to {new_folder_id}")
            
            # Update metadata in vector database without re-indexing content
            from services.silo_service import SiloService
            SiloService.update_resource_metadata(resource, db)
            logger.info(f"Updated metadata for resource {resource_id} with new folder information")
            
            return {
                "success": True,
                "message": "Resource moved successfully",
                "resource_id": resource_id,
                "new_folder_id": new_folder_id,
                "new_path": new_path
            }
            
        except Exception as e:
            logger.error(f"Error moving resource {resource_id}: {str(e)}")
            raise ValueError(f"Failed to move resource: {str(e)}")

    @staticmethod
    def delete_resource(resource_id: int, db: Session) -> bool:
        """
        Delete a resource completely (file, database record, and silo indexing)
        
        Args:
            resource_id: The ID of the resource to delete
            db: Database session
            
        Returns:
            True if deletion was successful, False if resource not found
        """
        resource = ResourceRepository.get_by_id(db, resource_id)
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
            ResourceRepository.delete(db, resource)
            ResourceRepository.commit(db)
            logger.info(f"Resource {resource_id} deleted from database")
            
            return True
            
        except Exception as e:
            logger.error(f"Error deleting resource {resource_id}: {str(e)}")
            ResourceRepository.rollback(db)
            return False
    
    @staticmethod
    def get_resource_file_path(resource_id: int, db: Session) -> Optional[str]:
        """
        Get the file path for a resource
        
        Args:
            resource_id: The ID of the resource
            db: Database session
            
        Returns:
            The full file path or None if resource not found
        """
        resource = ResourceService.get_resource(resource_id, db)
        if not resource:
            return None
        
        # Build path including folder structure
        if resource.folder_id:
            folder_path = FolderService.get_folder_path(resource.folder_id, db)
            return os.path.join(REPO_BASE_FOLDER, str(resource.repository_id), folder_path, resource.uri)
        else:
            # Resource is at root level
            return os.path.join(REPO_BASE_FOLDER, str(resource.repository_id), resource.uri)
    
    @staticmethod
    def create_multiple_resources(files: List, repository_id: int, db: Session, custom_names: dict = None, folder_id: Optional[int] = None) -> Tuple[List[Resource], List[dict]]:
        """
        Create multiple resources from uploaded files
        
        Args:
            files: List of uploaded files
            repository_id: The ID of the repository
            db: Database session
            custom_names: Dictionary mapping file indices to custom names (without extensions)
            folder_id: Optional folder ID to upload files to
            
        Returns:
            Tuple containing a list of created Resource instances and a list of failed files
            
        Raises:
            ValueError: If any file is invalid or missing
        """
        if not files:
            raise ValueError("No files provided")
        
        if custom_names is None:
            custom_names = {}
        
        # Validate folder_id if provided
        if folder_id is not None:
            logger.info(f"Validating folder access: folder_id={folder_id}, repository_id={repository_id}")
            if not FolderService.validate_folder_access(folder_id, repository_id, db):
                logger.error(f"Folder {folder_id} does not belong to repository {repository_id}")
                raise ValueError(f"Folder {folder_id} does not belong to repository {repository_id}")
            logger.info(f"Folder access validated successfully")
        
        # Build the target path
        repository_path = os.path.join(REPO_BASE_FOLDER, str(repository_id))
        if folder_id:
            folder_path = FolderService.get_folder_path(folder_id, db)
            target_path = os.path.join(repository_path, folder_path)
            logger.info(f"Building path for folder: repository_path={repository_path}, folder_path={folder_path}, target_path={target_path}")
        else:
            target_path = repository_path
            logger.info(f"Building path for root: target_path={target_path}")
        
        os.makedirs(target_path, exist_ok=True)

        created_resources = []
        failed_files = []
        
        for index, file in enumerate(files):
            custom_name = custom_names.get(index)
            result = ResourceService._process_single_file(file, repository_id, target_path, custom_name, folder_id, db)
            if isinstance(result, Resource):
                created_resources.append(result)
                logger.info(f"Resource {result.name} prepared for indexing")
            else:
                failed_files.append(result)

        if created_resources:
            try:
                ResourceRepository.commit(db)
                logger.info(f"Successfully saved {len(created_resources)} resources to database")
                ResourceService._index_resources(created_resources)
            except Exception as e:
                logger.error(f"Error committing resources to database: {str(e)}")
                ResourceRepository.rollback(db)
                ResourceService._cleanup_files(created_resources, repository_path)
                raise

        if failed_files:
            logger.warning(f"Failed to process {len(failed_files)} files: {failed_files}")

        return created_resources, failed_files

    @staticmethod
    def _process_single_file(file, repository_id: int, target_path: str, custom_name: str = None, folder_id: Optional[int] = None, db: Session = None):
        """
        Process a single file upload
        
        Args:
            file: The uploaded file
            repository_id: The ID of the repository
            target_path: The path to save the file
            custom_name: Custom name for the resource (without extension)
            folder_id: Optional folder ID
            db: Database session to use
            
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
                folder_id=folder_id,
                type=file_extension  # Set the file type based on extension
            )
            file_path = os.path.join(target_path, save_filename)
            
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
            
            ResourceRepository.create(db, resource)
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

    # ==================== ROUTER SERVICE METHODS ====================
    
    @staticmethod
    def upload_resources_to_repository(
        app_id: int,
        repository_id: int,
        files: List[UploadFile],
        db: Session,
        folder_id: Optional[int] = None
    ) -> dict:
        """
        Upload multiple resources to a repository - business logic from router
        
        Args:
            app_id: Application ID
            repository_id: Repository ID
            files: List of uploaded files
            db: Database session
            folder_id: Optional folder ID to upload files to
            
        Returns:
            Dictionary with upload results
            
        Raises:
            HTTPException: If validation fails or repository not found
        """
        logger.info(f"Upload resources service called - app_id: {app_id}, repository_id: {repository_id}, files_count: {len(files)}")
        
        if not files:
            logger.warning("No files provided in upload request")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No files provided"
            )


        # Validate repository exists
        repo = ResourceRepository.get_repository_by_id(db, repository_id)
        if not repo:
            logger.error(f"Repository {repository_id} not found")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Repository not found"
            )
        
        logger.info(f"Repository {repository_id} found, processing {len(files)} files")
        
        # Process files using create_multiple_resources method
        created_resources, failed_files = ResourceService.create_multiple_resources(
            files, repository_id, db, folder_id=folder_id
        )
        
        logger.info(f"Upload completed - {len(created_resources)} resources created, {len(failed_files)} failed")
        
        return {
            "message": f"Successfully uploaded {len(created_resources)} files to repository {repository_id}",
            "created_resources": [
                {
                    "resource_id": r.resource_id,
                    "uri": r.uri,
                    "repository_id": r.repository_id,
                    "create_date": r.create_date,
                    "size": None,
                    "content_type": r.type or "unknown"
                } for r in created_resources
            ],
            "failed_files": failed_files
        }
    
    @staticmethod
    def delete_resource_from_repository(
        app_id: int,
        repository_id: int,
        resource_id: int,
        db: Session
    ) -> dict:
        """
        Delete a specific resource from a repository - business logic from router
        
        Args:
            app_id: Application ID
            repository_id: Repository ID
            resource_id: Resource ID to delete
            db: Database session
            
        Returns:
            Dictionary with deletion result
            
        Raises:
            HTTPException: If resource not found or could not be deleted
        """
        logger.info(f"Delete resource service called - app_id: {app_id}, repository_id: {repository_id}, resource_id: {resource_id}")
        
        # Use delete_resource method with database session
        success = ResourceService.delete_resource(resource_id, db)
        if not success:
            logger.error(f"Resource {resource_id} not found or could not be deleted")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Resource not found or could not be deleted"
            )
        
        logger.info(f"Resource {resource_id} deleted successfully")
        return {"message": "Resource deleted successfully"}
    
    @staticmethod
    def download_resource_from_repository(
        app_id: int,
        repository_id: int,
        resource_id: int,
        user_id: str,
        db: Session
    ) -> tuple:
        """
        Download a specific resource from a repository - business logic from router
        
        Args:
            app_id: Application ID
            repository_id: Repository ID
            resource_id: Resource ID to download
            user_id: User ID for logging
            db: Database session
            
        Returns:
            Tuple containing (file_path, filename) for FileResponse
            
        Raises:
            HTTPException: If resource not found or file doesn't exist
        """
        logger.info(f"Download request - app_id: {app_id}, repository_id: {repository_id}, resource_id: {resource_id}, user_id: {user_id}")
        
        # Get resource using method with database session
        resource = ResourceService.get_resource(resource_id, db)
        if not resource:
            logger.error(f"Resource {resource_id} not found")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Resource not found"
            )
        
        logger.info(f"Resource found: {resource.name}, uri: {resource.uri}, repository_id: {resource.repository_id}")
        
        # Get file path using method with database session
        file_path = ResourceService.get_resource_file_path(resource_id, db)
        logger.info(f"File path: {file_path}")
        
        if not file_path:
            logger.error(f"No file path returned for resource {resource_id}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="File path not found"
            )
        
        if not os.path.exists(file_path):
            logger.error(f"File does not exist at path: {file_path}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="File not found on disk"
            )
        
        logger.info(f"File exists, returning file info for: {file_path}")
        
        return file_path, resource.uri 