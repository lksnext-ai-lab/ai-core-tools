from models.folder import Folder
from repositories.folder_repository import FolderRepository
from repositories.repository_repository import RepositoryRepository
from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from fastapi import HTTPException, status
from utils.logger import get_logger

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
        Delete a folder and all its contents
        
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
        
        # Move the folder
        try:
            updated_folder = FolderRepository.move_folder(db, folder, new_parent_folder_id)
            FolderRepository.commit(db)
            logger.info(f"Moved folder {folder_id} to parent {new_parent_folder_id}")
            return updated_folder
        except Exception as e:
            FolderRepository.rollback(db)
            logger.error(f"Error moving folder: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to move folder"
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
