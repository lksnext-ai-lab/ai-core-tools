from sqlalchemy.orm import Session
from models.resource import Resource
from models.repository import Repository
from typing import List, Optional


class ResourceRepository:
    
    @staticmethod
    def get_by_repository_id(db: Session, repository_id: int) -> List[Resource]:
        """
        Get all resources by repository ID
        
        Args:
            db: Database session
            repository_id: Repository ID
            
        Returns:
            List of Resource instances
        """
        return db.query(Resource).filter(Resource.repository_id == repository_id).all()
    
    @staticmethod
    def get_by_id(db: Session, resource_id: int) -> Optional[Resource]:
        """
        Get a resource by its ID
        
        Args:
            db: Database session
            resource_id: Resource ID
            
        Returns:
            Resource instance or None if not found
        """
        return db.query(Resource).filter(Resource.resource_id == resource_id).first()
    
    @staticmethod
    def create(db: Session, resource: Resource) -> Resource:
        """
        Create a new resource
        
        Args:
            db: Database session
            resource: Resource instance to create
            
        Returns:
            Created Resource instance
        """
        db.add(resource)
        db.flush()
        return resource
    
    @staticmethod
    def create_multiple(db: Session, resources: List[Resource]) -> List[Resource]:
        """
        Create multiple resources
        
        Args:
            db: Database session
            resources: List of Resource instances to create
            
        Returns:
            List of created Resource instances
        """
        db.add_all(resources)
        db.flush()
        return resources
    
    @staticmethod
    def delete(db: Session, resource: Resource) -> None:
        """
        Delete a resource
        
        Args:
            db: Database session
            resource: Resource instance to delete
        """
        db.delete(resource)
    
    @staticmethod
    def commit(db: Session) -> None:
        """
        Commit the current transaction
        
        Args:
            db: Database session
        """
        db.commit()
    
    @staticmethod
    def rollback(db: Session) -> None:
        """
        Rollback the current transaction
        
        Args:
            db: Database session
        """
        db.rollback()
    
    @staticmethod
    def count_by_repository_id(db: Session, repository_id: int) -> int:
        """
        Count resources by repository ID
        
        Args:
            db: Database session
            repository_id: Repository ID
            
        Returns:
            Number of resources in the repository
        """
        return db.query(Resource).filter(Resource.repository_id == repository_id).count()
    
    @staticmethod
    def get_repository_by_id(db: Session, repository_id: int) -> Optional[Repository]:
        """
        Get a repository by its ID using RepositoryRepository
        
        Args:
            db: Database session
            repository_id: Repository ID
            
        Returns:
            Repository instance or None if not found
        """
        from repositories.repository_repository import RepositoryRepository
        return RepositoryRepository.get_by_id(db, repository_id)
    
    @staticmethod
    def check_uri_conflict(db: Session, repository_id: int, folder_id: Optional[int], uri: str) -> bool:
        """
        Check if a resource URI already exists in the same folder
        
        Args:
            db: Database session
            repository_id: Repository ID
            folder_id: Folder ID (None for root level)
            uri: Resource URI to check
            
        Returns:
            True if URI conflict exists, False otherwise
        """
        # Handle NULL comparison properly for folder_id
        folder_filter = (
            Resource.folder_id.is_(None)
            if folder_id is None
            else Resource.folder_id == folder_id
        )
        
        return db.query(Resource).filter(
            Resource.repository_id == repository_id,
            folder_filter,
            Resource.uri == uri
        ).first() is not None
