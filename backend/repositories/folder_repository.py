from sqlalchemy.orm import Session
from models.folder import Folder
from models.resource import Resource
from typing import List, Optional, Dict, Any
from sqlalchemy import and_, or_


class FolderRepository:
    
    @staticmethod
    def get_by_id(db: Session, folder_id: int) -> Optional[Folder]:
        """
        Get a folder by its ID
        
        Args:
            db: Database session
            folder_id: Folder ID
            
        Returns:
            Folder instance or None if not found
        """
        return db.query(Folder).filter(Folder.folder_id == folder_id).first()
    
    @staticmethod
    def get_by_repository_id(db: Session, repository_id: int) -> List[Folder]:
        """
        Get all root folders (parent_folder_id is None) for a repository
        
        Args:
            db: Database session
            repository_id: Repository ID
            
        Returns:
            List of root Folder instances
        """
        return db.query(Folder).filter(
            and_(
                Folder.repository_id == repository_id,
                Folder.parent_folder_id.is_(None)
            )
        ).all()
    
    @staticmethod
    def get_subfolders(db: Session, parent_folder_id: int) -> List[Folder]:
        """
        Get all direct child folders of a parent folder
        
        Args:
            db: Database session
            parent_folder_id: Parent folder ID
            
        Returns:
            List of child Folder instances
        """
        return db.query(Folder).filter(Folder.parent_folder_id == parent_folder_id).all()
    
    @staticmethod
    def get_folder_tree(db: Session, repository_id: int, parent_folder_id: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        Get the complete folder tree structure for a repository
        
        Args:
            db: Database session
            repository_id: Repository ID
            parent_folder_id: Parent folder ID (None for root level)
            
        Returns:
            List of folder dictionaries with nested subfolders
        """
        if parent_folder_id is None:
            # Get root folders
            folders = db.query(Folder).filter(
                and_(
                    Folder.repository_id == repository_id,
                    Folder.parent_folder_id.is_(None)
                )
            ).all()
        else:
            # Get child folders
            folders = db.query(Folder).filter(Folder.parent_folder_id == parent_folder_id).all()
        
        result = []
        for folder in folders:
            folder_dict = folder.to_dict()
            # Recursively get subfolders
            folder_dict['subfolders'] = FolderRepository.get_folder_tree(db, repository_id, folder.folder_id)
            # Get resource count for this folder
            folder_dict['resource_count'] = db.query(Resource).filter(Resource.folder_id == folder.folder_id).count()
            result.append(folder_dict)
        
        return result
    
    @staticmethod
    def get_folder_path(db: Session, folder_id: int) -> str:
        """
        Compute the full path from root to a folder
        
        Args:
            db: Database session
            folder_id: Folder ID
            
        Returns:
            Full path string (e.g., "docs/2024/reports")
        """
        folder = FolderRepository.get_by_id(db, folder_id)
        if not folder:
            return ""
        
        return folder.get_path()
    
    @staticmethod
    def create(db: Session, folder: Folder) -> Folder:
        """
        Create a new folder
        
        Args:
            db: Database session
            folder: Folder instance to create
            
        Returns:
            Created Folder instance
        """
        db.add(folder)
        db.flush()
        return folder
    
    @staticmethod
    def update(db: Session, folder: Folder) -> Folder:
        """
        Update an existing folder
        
        Args:
            db: Database session
            folder: Folder instance to update
            
        Returns:
            Updated Folder instance
        """
        db.merge(folder)
        db.flush()
        return folder
    
    @staticmethod
    def delete(db: Session, folder: Folder) -> None:
        """
        Delete a folder and all its subfolders (cascade).
        Note: Resources should be deleted separately using ResourceService.delete_resource()
        to ensure proper cleanup of files and indexed data.
        
        Args:
            db: Database session
            folder: Folder instance to delete
        """
        # Recursively delete all subfolders first
        subfolders = FolderRepository.get_subfolders(db, folder.folder_id)
        for subfolder in subfolders:
            FolderRepository.delete(db, subfolder)
        
        # Delete the folder itself
        db.delete(folder)
        db.flush()
    
    @staticmethod
    def move_folder(db: Session, folder: Folder, new_parent_folder_id: Optional[int]) -> Folder:
        """
        Move a folder to a new parent
        
        Args:
            db: Database session
            folder: Folder instance to move
            new_parent_folder_id: New parent folder ID (None for root level)
            
        Returns:
            Updated Folder instance
        """
        folder.parent_folder_id = new_parent_folder_id
        return FolderRepository.update(db, folder)
    
    @staticmethod
    def check_name_conflict(db: Session, repository_id: int, name: str, parent_folder_id: Optional[int], exclude_folder_id: Optional[int] = None) -> bool:
        """
        Check if a folder name already exists in the same parent folder
        
        Args:
            db: Database session
            repository_id: Repository ID
            name: Folder name to check
            parent_folder_id: Parent folder ID (None for root level)
            exclude_folder_id: Folder ID to exclude from check (for updates)
            
        Returns:
            True if name conflict exists, False otherwise
        """
        query = db.query(Folder).filter(
            and_(
                Folder.repository_id == repository_id,
                Folder.name == name,
                Folder.parent_folder_id == parent_folder_id
            )
        )
        
        if exclude_folder_id:
            query = query.filter(Folder.folder_id != exclude_folder_id)
        
        return query.first() is not None
    
    @staticmethod
    def check_circular_reference(db: Session, folder_id: int, new_parent_folder_id: int) -> bool:
        """
        Check if moving a folder would create a circular reference
        
        Args:
            db: Database session
            folder_id: Folder ID to move
            new_parent_folder_id: Proposed new parent folder ID
            
        Returns:
            True if circular reference would be created, False otherwise
        """
        if folder_id == new_parent_folder_id:
            return True
        
        # Check if new_parent_folder_id is a descendant of folder_id
        current_parent = new_parent_folder_id
        while current_parent is not None:
            if current_parent == folder_id:
                return True
            parent_folder = FolderRepository.get_by_id(db, current_parent)
            if not parent_folder:
                break
            current_parent = parent_folder.parent_folder_id
        
        return False
    
    @staticmethod
    def get_all_folders_in_repository(db: Session, repository_id: int) -> List[Folder]:
        """
        Get all folders in a repository (flat list)
        
        Args:
            db: Database session
            repository_id: Repository ID
            
        Returns:
            List of all Folder instances in the repository
        """
        return db.query(Folder).filter(Folder.repository_id == repository_id).all()
    
    @staticmethod
    def commit(db: Session) -> None:
        """Commit the current transaction"""
        db.commit()
    
    @staticmethod
    def rollback(db: Session) -> None:
        """Rollback the current transaction"""
        db.rollback()
