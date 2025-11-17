from models.folder import Folder
from repositories.folder_repository import FolderRepository
from repositories.repository_repository import RepositoryRepository
from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from fastapi import HTTPException, status
from utils.logger import get_logger
import shutil
import os

logger = get_logger(__name__)

# Constants
FOLDER_NOT_FOUND_MSG = "Folder not found"


class FolderService:
    
    @staticmethod
    def get_folder_by_id(folder_id: int, db: Session) -> Optional[Folder]:
        """
        Get a folder by its ID
        
        Args:
            folder_id: Folder ID
            db: Database session
            
        Returns:
            Folder instance or None if not found
        """
        return FolderRepository.get_by_id(db, folder_id)
    
    @staticmethod
    def get_root_folders(repository_id: int, db: Session) -> List[Folder]:
        """
        Get all root folders for a repository
        
        Args:
            repository_id: Repository ID
            db: Database session
            
        Returns:
            List of root Folder instances
        """
        return FolderRepository.get_by_repository_id(db, repository_id)
    
    @staticmethod
    def get_folder_tree(repository_id: int, db: Session) -> List[Dict[str, Any]]:
        """
        Get the complete folder tree structure for a repository
        
        Args:
            repository_id: Repository ID
            db: Database session
            
        Returns:
            List of folder dictionaries with nested subfolders
        """
        return FolderRepository.get_folder_tree(db, repository_id)
    
    @staticmethod
    def get_folder_path(folder_id: int, db: Session) -> str:
        """
        Get the full path from root to a folder
        
        Args:
            folder_id: Folder ID
            db: Database session
            
        Returns:
            Full path string (e.g., "docs/2024/reports")
        """
        return FolderRepository.get_folder_path(db, folder_id)
    
    @staticmethod
    def create_folder(
        repository_id: int, 
        name: str, 
        parent_folder_id: Optional[int], 
        db: Session
    ) -> Folder:
        """
        Create a new folder
        
        Args:
            repository_id: Repository ID
            name: Folder name
            parent_folder_id: Parent folder ID (None for root level)
            db: Database session
            
        Returns:
            Created Folder instance
            
        Raises:
            HTTPException: If validation fails
        """
        # Validate repository exists
        repository = RepositoryRepository.get_by_id(db, repository_id)
        if not repository:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Repository not found"
            )
        
        # Validate folder name
        if not name or not name.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Folder name cannot be empty"
            )
        
        name = name.strip()
        
        # Check for name conflicts
        if FolderRepository.check_name_conflict(db, repository_id, name, parent_folder_id):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Folder '{name}' already exists in this location"
            )
        
        # Validate parent folder if specified
        if parent_folder_id is not None:
            parent_folder = FolderRepository.get_by_id(db, parent_folder_id)
            if not parent_folder:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Parent folder not found"
                )
            if parent_folder.repository_id != repository_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Parent folder does not belong to this repository"
                )
        
        # Create the folder
        folder = Folder(
            name=name,
            repository_id=repository_id,
            parent_folder_id=parent_folder_id,
            status='active'
        )
        
        try:
            created_folder = FolderRepository.create(db, folder)
            FolderRepository.commit(db)
            logger.info(f"Created folder '{name}' in repository {repository_id}")
            return created_folder
        except Exception as e:
            FolderRepository.rollback(db)
            logger.error(f"Error creating folder: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create folder"
            )
    
    @staticmethod
    def update_folder(
        folder_id: int, 
        name: str, 
        db: Session
    ) -> Folder:
        """
        Update a folder's name
        
        Args:
            folder_id: Folder ID
            name: New folder name
            db: Database session
            
        Returns:
            Updated Folder instance
            
        Raises:
            HTTPException: If validation fails
        """
        folder = FolderRepository.get_by_id(db, folder_id)
        if not folder:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=FOLDER_NOT_FOUND_MSG
            )
        
        # Validate folder name
        if not name or not name.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Folder name cannot be empty"
            )
        
        name = name.strip()
        
        # Check for name conflicts (excluding current folder)
        if FolderRepository.check_name_conflict(
            db, 
            folder.repository_id, 
            name, 
            folder.parent_folder_id, 
            exclude_folder_id=folder_id
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Folder '{name}' already exists in this location"
            )
        
        # Update the folder
        folder.name = name
        
        try:
            updated_folder = FolderRepository.update(db, folder)
            FolderRepository.commit(db)
            logger.info(f"Updated folder {folder_id} name to '{name}'")
            return updated_folder
        except Exception as e:
            FolderRepository.rollback(db)
            logger.error(f"Error updating folder: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to update folder"
            )
    
    @staticmethod
    def delete_folder(folder_id: int, db: Session) -> None:
        """
        Delete a folder and all its contents (files, database records, and indexed data)
        
        Args:
            folder_id: Folder ID
            db: Database session
            
        Raises:
            HTTPException: If folder not found
        """
        folder = FolderRepository.get_by_id(db, folder_id)
        if not folder:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=FOLDER_NOT_FOUND_MSG
            )
        
        try:
            # First, delete all resources in this folder and its subfolders properly
            FolderService._delete_all_resources_in_folder(folder_id, db)
            
            # Then delete the folder structure from filesystem
            FolderService._delete_folder_from_filesystem(folder_id, db)
            
            # Finally delete the folder structure from database
            FolderRepository.delete(db, folder)
            FolderRepository.commit(db)
            logger.info(f"Deleted folder {folder_id} and all its contents")
        except Exception as e:
            FolderRepository.rollback(db)
            logger.error(f"Error deleting folder: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to delete folder"
            )
    
    @staticmethod
    def move_folder(
        folder_id: int, 
        new_parent_folder_id: Optional[int], 
        db: Session
    ) -> Folder:
        """
        Move a folder to a new parent
        
        Args:
            folder_id: Folder ID to move
            new_parent_folder_id: New parent folder ID (None for root level)
            db: Database session
            
        Returns:
            Updated Folder instance
            
        Raises:
            HTTPException: If validation fails
        """
        folder = FolderRepository.get_by_id(db, folder_id)
        if not folder:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=FOLDER_NOT_FOUND_MSG
            )
        
        # Validate new parent folder if specified
        if new_parent_folder_id is not None:
            new_parent = FolderRepository.get_by_id(db, new_parent_folder_id)
            if not new_parent:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="New parent folder not found"
                )
            if new_parent.repository_id != folder.repository_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="New parent folder does not belong to the same repository"
                )
        
        # Check for circular reference
        if FolderRepository.check_circular_reference(db, folder_id, new_parent_folder_id):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot move folder: would create circular reference"
            )
        
        # Check for name conflicts in new location
        if FolderRepository.check_name_conflict(
            db, 
            folder.repository_id, 
            folder.name, 
            new_parent_folder_id, 
            exclude_folder_id=folder_id
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Folder '{folder.name}' already exists in the target location"
            )
        
        # Move the folder with proper rollback mechanism
        old_folder_path = None
        new_folder_path = None
        
        try:
            # Calculate paths before moving
            old_folder_path = FolderService.get_folder_path(folder_id, db)
            folder = FolderRepository.get_by_id(db, folder_id)
            
            if new_parent_folder_id:
                new_parent_path = FolderService.get_folder_path(new_parent_folder_id, db)
                new_folder_path = f"{new_parent_path}/{folder.name}"
            else:
                new_folder_path = folder.name  # Moving to root
            
            # First, move all files in the filesystem using existing file move logic
            FolderService._move_folder_files_using_existing_logic(folder_id, new_parent_folder_id, db)
            
            # Then update the database
            updated_folder = FolderRepository.move_folder(db, folder, new_parent_folder_id)
            FolderRepository.commit(db)
            logger.info(f"Moved folder {folder_id} to parent {new_parent_folder_id}")
            
            # Update metadata for all resources in this folder and its subfolders
            FolderService._update_resources_metadata_after_folder_move(folder_id, db)
            
            return updated_folder
        except Exception as e:
            # Rollback filesystem changes if database update failed
            if old_folder_path and new_folder_path:
                try:
                    from services.resource_service import REPO_BASE_FOLDER
                    
                    repository_path = os.path.join(REPO_BASE_FOLDER, str(folder.repository_id))
                    old_full_path = os.path.join(repository_path, old_folder_path)
                    new_full_path = os.path.join(repository_path, new_folder_path)
                    
                    # Move folder back to original location
                    if os.path.exists(new_full_path) and os.path.exists(os.path.dirname(old_full_path)):
                        shutil.move(new_full_path, old_full_path)
                        logger.info(f"Rolled back filesystem move: {new_full_path} -> {old_full_path}")
                except Exception as rollback_error:
                    logger.error(f"Failed to rollback filesystem changes: {str(rollback_error)}")
            
            FolderRepository.rollback(db)
            logger.error(f"Error moving folder: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to move folder: {str(e)}"
            )
    
    @staticmethod
    def get_folder_with_contents(folder_id: int, db: Session) -> Optional[Dict[str, Any]]:
        """
        Get a folder with its subfolders and resources
        
        Args:
            folder_id: Folder ID
            db: Database session
            
        Returns:
            Folder dictionary with subfolders and resources, or None if not found
        """
        folder = FolderRepository.get_by_id(db, folder_id)
        if not folder:
            return None
        
        return folder.to_dict(include_children=True)
    
    @staticmethod
    def validate_folder_access(folder_id: int, repository_id: int, db: Session) -> bool:
        """
        Validate that a folder belongs to the specified repository
        
        Args:
            folder_id: Folder ID
            repository_id: Repository ID
            db: Database session
            
        Returns:
            True if folder belongs to repository, False otherwise
        """
        folder = FolderRepository.get_by_id(db, folder_id)
        return folder is not None and folder.repository_id == repository_id
    
    @staticmethod
    def get_all_folders_in_repository(repository_id: int, db: Session) -> List[Folder]:
        """
        Get all folders in a repository (flat list)
        
        Args:
            repository_id: Repository ID
            db: Database session
            
        Returns:
            List of all Folder instances in the repository
        """
        return FolderRepository.get_all_folders_in_repository(db, repository_id)
    
    @staticmethod
    def _update_resources_metadata_after_folder_move(folder_id: int, db: Session) -> None:
        """
        Update metadata for all resources in a moved folder and its subfolders.
        This is called after a folder has been moved to update vector database metadata.
        
        Args:
            folder_id: ID of the moved folder
            db: Database session
        """
        try:
            from services.silo_service import SiloService
            from models.resource import Resource
            
            # Get ALL folder IDs recursively in one query to avoid multiple processing
            all_folder_ids = FolderService._get_all_subfolder_ids_recursive(folder_id, db)
            all_folder_ids.append(folder_id)  # Include the moved folder itself
            
            # Get all resources in one query
            resources_to_update = db.query(Resource).filter(
                Resource.folder_id.in_(all_folder_ids)
            ).all()
            
            # Update metadata for all found resources
            failed_updates = []
            for resource in resources_to_update:
                try:
                    logger.info(f"Updating metadata for resource {resource.resource_id} after folder move")
                    SiloService.update_resource_metadata(resource, db)
                except Exception as resource_error:
                    logger.error(f"Failed to update metadata for resource {resource.resource_id}: {str(resource_error)}")
                    failed_updates.append(resource.resource_id)
            
            if failed_updates:
                logger.warning(f"Failed to update metadata for {len(failed_updates)} resources: {failed_updates}")
            else:
                logger.info(f"Updated metadata for {len(resources_to_update)} resources after folder {folder_id} move")
            
        except Exception as e:
            logger.error(f"Error updating resources metadata after folder move: {str(e)}")
            # Don't raise exception here to avoid breaking the folder move operation
    
    @staticmethod
    def _get_all_subfolder_ids_recursive(folder_id: int, db: Session) -> List[int]:
        """
        Get all subfolder IDs recursively for a given folder.
        
        Args:
            folder_id: ID of the parent folder
            db: Database session
            
        Returns:
            List of all subfolder IDs
        """
        all_subfolder_ids = []
        subfolders = FolderRepository.get_subfolders(db, folder_id)
        
        for subfolder in subfolders:
            all_subfolder_ids.append(subfolder.folder_id)
            # Recursively get subfolders of subfolders
            all_subfolder_ids.extend(FolderService._get_all_subfolder_ids_recursive(subfolder.folder_id, db))
        
        return all_subfolder_ids
    
    @staticmethod
    def _delete_all_resources_in_folder(folder_id: int, db: Session) -> None:
        """
        Delete all resources in a folder and its subfolders properly.
        This includes deleting files from disk and indexed data from vector database.
        
        Args:
            folder_id: ID of the folder to delete resources from
            db: Database session
        """
        try:
            from services.resource_service import ResourceService
            from models.resource import Resource
            
            # Get all folder IDs recursively (including the folder itself and all subfolders)
            all_folder_ids = FolderService._get_all_subfolder_ids_recursive(folder_id, db)
            all_folder_ids.append(folder_id)  # Include the folder itself
            
            # Get all resources in these folders
            resources_to_delete = db.query(Resource).filter(
                Resource.folder_id.in_(all_folder_ids)
            ).all()
            
            # Delete each resource properly using the existing ResourceService method
            deleted_count = 0
            failed_deletions = []
            
            for resource in resources_to_delete:
                try:
                    success = ResourceService.delete_resource(resource.resource_id, db)
                    if success:
                        deleted_count += 1
                        logger.info(f"Successfully deleted resource {resource.resource_id}: {resource.name}")
                    else:
                        failed_deletions.append(resource.resource_id)
                        logger.error(f"Failed to delete resource {resource.resource_id}: {resource.name}")
                except Exception as resource_error:
                    failed_deletions.append(resource.resource_id)
                    logger.error(f"Error deleting resource {resource.resource_id}: {str(resource_error)}")
            
            if failed_deletions:
                logger.warning(f"Failed to delete {len(failed_deletions)} resources: {failed_deletions}")
            else:
                logger.info(f"Successfully deleted {deleted_count} resources from folder {folder_id} and its subfolders")
                
        except Exception as e:
            logger.error(f"Error deleting resources in folder {folder_id}: {str(e)}")
            # Don't raise exception here to avoid breaking the folder deletion operation
            # The folder structure will still be deleted from database
    
    @staticmethod
    def _delete_folder_from_filesystem(folder_id: int, db: Session) -> None:
        """
        Delete the folder structure from the filesystem.
        This should be called after all resources in the folder have been deleted.
        
        Args:
            folder_id: ID of the folder to delete from filesystem
            db: Database session
        """
        try:
            from services.resource_service import REPO_BASE_FOLDER
            
            # Get the folder path
            folder_path = FolderService.get_folder_path(folder_id, db)
            folder = FolderRepository.get_by_id(db, folder_id)
            
            if not folder:
                logger.error(f"Folder {folder_id} not found for filesystem deletion")
                return
            
            # Build the full filesystem path
            repository_path = os.path.join(REPO_BASE_FOLDER, str(folder.repository_id))
            full_folder_path = os.path.join(repository_path, folder_path)
            
            logger.info(f"Deleting folder from filesystem: {full_folder_path}")
            
            # Delete the folder and all its contents from filesystem
            if os.path.exists(full_folder_path):
                import shutil
                shutil.rmtree(full_folder_path)
                logger.info(f"Successfully deleted folder from filesystem: {full_folder_path}")
            else:
                logger.warning(f"Folder path does not exist in filesystem: {full_folder_path}")
                
        except Exception as e:
            logger.error(f"Error deleting folder from filesystem: {str(e)}")
            # Don't raise exception here to avoid breaking the folder deletion operation
    
    @staticmethod
    def _move_folder_files_using_existing_logic(folder_id: int, new_parent_folder_id: Optional[int], db: Session) -> None:
        """
        Move the entire folder structure in the filesystem.
        This moves the folder as a unit, not individual files.
        
        Args:
            folder_id: ID of the folder being moved
            new_parent_folder_id: New parent folder ID (None for root)
            db: Database session
        """
        try:
            from services.resource_service import REPO_BASE_FOLDER
            
            # Get the folder being moved
            folder = FolderRepository.get_by_id(db, folder_id)
            if not folder:
                logger.error(f"Folder {folder_id} not found for filesystem move")
                return
            
            # Calculate old and new folder paths
            old_folder_path = FolderService.get_folder_path(folder_id, db)
            if new_parent_folder_id:
                new_parent_path = FolderService.get_folder_path(new_parent_folder_id, db)
                new_folder_path = os.path.join(new_parent_path, folder.name)
            else:
                new_folder_path = folder.name  # Moving to root
            
            # Build full filesystem paths
            repository_path = os.path.join(REPO_BASE_FOLDER, str(folder.repository_id))
            old_full_path = os.path.join(repository_path, old_folder_path)
            new_full_path = os.path.join(repository_path, new_folder_path)
            
            logger.info(f"Moving entire folder from {old_full_path} to {new_full_path}")
            
            # Create target directory if it doesn't exist
            # Handle edge case for root folder moves
            target_dir = os.path.dirname(new_full_path)
            if target_dir and target_dir != repository_path:
                os.makedirs(target_dir, exist_ok=True)
            elif not new_parent_folder_id:  # Moving to root
                # Ensure repository directory exists
                os.makedirs(repository_path, exist_ok=True)
            
            # Move the entire folder and all its contents as a unit
            if os.path.exists(old_full_path):
                shutil.move(old_full_path, new_full_path)
                logger.info(f"Successfully moved entire folder {folder_id} from {old_full_path} to {new_full_path}")
            else:
                logger.warning(f"Source folder path {old_full_path} does not exist")
            
        except Exception as e:
            logger.error(f"Error moving folder in filesystem: {str(e)}")
            raise  # Re-raise to trigger rollback
