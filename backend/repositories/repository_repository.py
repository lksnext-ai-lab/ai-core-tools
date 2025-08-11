from sqlalchemy.orm import Session
from models.repository import Repository
from typing import List, Optional


class RepositoryRepository:
    
    @staticmethod
    def get_by_id(db: Session, repository_id: int) -> Optional[Repository]:
        """
        Get a repository by its ID
        
        Args:
            db: Database session
            repository_id: Repository ID
            
        Returns:
            Repository instance or None if not found
        """
        return db.query(Repository).filter(Repository.repository_id == repository_id).first()
    
    @staticmethod
    def get_by_app_id(db: Session, app_id: int) -> List[Repository]:
        """
        Get all repositories by app ID
        
        Args:
            db: Database session
            app_id: Application ID
            
        Returns:
            List of Repository instances
        """
        return db.query(Repository).filter(Repository.app_id == app_id).all()
    
    @staticmethod
    def create(db: Session, repository: Repository) -> Repository:
        """
        Create a new repository
        
        Args:
            db: Database session
            repository: Repository instance to create
            
        Returns:
            Created Repository instance
        """
        db.add(repository)
        db.commit()
        db.refresh(repository)
        return repository
    
    @staticmethod
    def update(db: Session, repository: Repository) -> Repository:
        """
        Update an existing repository
        
        Args:
            db: Database session
            repository: Repository instance to update
            
        Returns:
            Updated Repository instance
        """
        db.add(repository)
        db.commit()
        db.refresh(repository)
        return repository
    
    @staticmethod
    def delete(db: Session, repository: Repository) -> None:
        """
        Delete a repository
        
        Args:
            db: Database session
            repository: Repository instance to delete
        """
        db.delete(repository)
        db.commit()
    
    @staticmethod
    def delete_resources_by_repository_id(db: Session, repository_id: int) -> None:
        """
        Delete all resources for a repository using ResourceRepository
        
        Args:
            db: Database session
            repository_id: Repository ID
        """
        from repositories.resource_repository import ResourceRepository
        resources = ResourceRepository.get_by_repository_id(db, repository_id)
        for resource in resources:
            ResourceRepository.delete(db, resource)
        ResourceRepository.commit(db)
    
    @staticmethod
    def get_resources_by_repository_id(db: Session, repository_id: int):
        """
        Get all resources for a repository using ResourceRepository
        
        Args:
            db: Database session
            repository_id: Repository ID
            
        Returns:
            List of Resource instances for the repository
        """
        from repositories.resource_repository import ResourceRepository
        return ResourceRepository.get_by_repository_id(db, repository_id)
    
    @staticmethod
    def delete_output_parser_by_id(db: Session, parser_id: int) -> bool:
        """
        Delete an output parser by its ID using OutputParserRepository
        
        Args:
            db: Database session
            parser_id: Parser ID to delete
            
        Returns:
            True if deletion was successful, False otherwise
        """
        from repositories.output_parser_repository import OutputParserRepository
        parser_repo = OutputParserRepository()
        return parser_repo.delete_by_id(db, parser_id)
