from models.repository import Repository
from models.resource import Resource
from models.output_parser import OutputParser
from models.embedding_service import EmbeddingService
from db.database import SessionLocal
from sqlalchemy.orm import Session
from typing import Optional, List, Dict, Any
import os
import shutil
import config
from dotenv import load_dotenv
from services.silo_service import SiloService
from models.silo import SiloType
from services.output_parser_service import OutputParserService
from repositories.repository_repository import RepositoryRepository
from repositories.resource_repository import ResourceRepository
from repositories.embedding_service_repository import EmbeddingServiceRepository
from schemas.repository_schemas import RepositoryListItemSchema, RepositoryDetailSchema, CreateUpdateRepositorySchema
from datetime import datetime
from utils.logger import get_logger
from tools.vector_store_factory import VectorStoreFactory

load_dotenv()
REPO_BASE_FOLDER = os.path.abspath(os.getenv("REPO_BASE_FOLDER"))
logger = get_logger(__name__)

class RepositoryService:

    # ==================== BASIC CRUD OPERATIONS ====================

    @staticmethod
    def get_repository(repository_id: int, db: Session) -> Optional[Repository]:
        """
        Get a repository by its ID
        
        Args:
            repository_id: Repository ID
            db: Database session
            
        Returns:
            Repository instance or None if not found
        """
        return RepositoryRepository.get_by_id(db, repository_id)
    
    @staticmethod
    def get_repositories_by_app_id(app_id: int, db: Session) -> List[Repository]:
        """
        Get all repositories by app ID
        
        Args:
            app_id: Application ID
            db: Database session
            
        Returns:
            List of Repository instances
        """
        return RepositoryRepository.get_by_app_id(db, app_id)
    
    @staticmethod
    def create_repository(
        repository: Repository,
        embedding_service_id: Optional[int] = None,
        vector_db_type: Optional[str] = None,
        db: Session = None
    ) -> Repository:
        """
        Create a new repository with its associated silo
        
        Args:
            repository: Repository instance to create
            embedding_service_id: Optional embedding service ID for the silo
            db: Database session
            
        Returns:
            Created Repository instance
        """
        # First create the output parser for the repository
        output_parser_service = OutputParserService()
        parser_id = output_parser_service.create_default_filter_for_repo(db, repository)

        resolved_vector_db_type = (vector_db_type or config.VECTOR_DB_TYPE or 'PGVECTOR')
        if isinstance(resolved_vector_db_type, str):
            resolved_vector_db_type = resolved_vector_db_type.upper()
        
        # Create the silo with the correct metadata_definition_id
        silo_service = SiloService()
        silo_data = {
            'silo_id': 0,
            'name': 'silo for repository ' + repository.name,
            'description': 'silo for repository ' + repository.name,
            'status': 'active',
            'app_id': repository.app_id,
            'fixed_metadata': False,
            'metadata_definition_id': parser_id,
            'embedding_service_id': embedding_service_id,
            'vector_db_type': resolved_vector_db_type
        }
        silo = silo_service.create_or_update_silo(silo_data, SiloType.REPO, db)
        
        # Now create the repository with the silo_id
        repository.silo_id = silo.silo_id
        created_repository = RepositoryRepository.create(db, repository)
        
        # Create repository folder
        repo_folder = os.path.join(REPO_BASE_FOLDER, str(created_repository.repository_id))
        os.makedirs(repo_folder, exist_ok=True)
        
        return created_repository
    
    @staticmethod
    def update_repository(
        repository: Repository,
        embedding_service_id: Optional[int] = None,
        vector_db_type: Optional[str] = None,
        db: Session = None
    ) -> Repository:
        """
        Update an existing repository
        
        Args:
            repository: Repository instance to update
            embedding_service_id: Optional embedding service ID for the silo
            db: Database session
            
        Returns:
            Updated Repository instance
        """
        if repository.silo and embedding_service_id:
            repository.silo.embedding_service_id = embedding_service_id

        if repository.silo:
            if vector_db_type is not None:
                normalized_type = vector_db_type.upper()
                repository.silo.vector_db_type = normalized_type
            elif not repository.silo.vector_db_type:
                default_type = config.VECTOR_DB_TYPE or 'PGVECTOR'
                repository.silo.vector_db_type = default_type.upper() if isinstance(default_type, str) else default_type

        return RepositoryRepository.update(db, repository)
    
    @staticmethod
    def delete_repository(repository: Repository, db: Session):
        """
        Delete a repository and all its associated resources and data
        
        Args:
            repository: Repository instance to delete
            db: Database session
        """
        if not repository:
            return
        
        # Get silo and parser info before deletion
        silo = repository.silo
        parser_id = silo.metadata_definition_id if silo else None
        
        # Delete all resources first
        resources = RepositoryRepository.get_resources_by_repository_id(db, repository.repository_id)
        for resource in resources:
            # Delete the physical file if exists
            file_path = os.path.join(REPO_BASE_FOLDER, str(repository.repository_id), resource.uri)
            if os.path.exists(file_path):
                try:
                    os.remove(file_path)
                except OSError:
                    pass  # Ignore errors if file cannot be deleted
        
        # Delete all resource records
        RepositoryRepository.delete_resources_by_repository_id(db, repository.repository_id)
        
        # Delete repository folder if exists
        repo_folder = os.path.join(REPO_BASE_FOLDER, str(repository.repository_id))
        if os.path.exists(repo_folder):
            try:
                shutil.rmtree(repo_folder)
            except OSError:
                pass  # Ignore errors if folder cannot be deleted
            
        # Delete repository FIRST (before silo)
        RepositoryRepository.delete(db, repository)
        
        # Delete vector collection and silo SECOND (after repository is gone)
        if silo:
            SiloService.delete_collection(silo.silo_id, db)
            db.delete(silo)
            db.commit()
        
        # Delete output parser LAST (after silo is deleted)
        if parser_id:
            RepositoryRepository.delete_output_parser_by_id(db, parser_id)

    # ==================== ROUTER SERVICE METHODS ====================

    @staticmethod
    def get_repositories_list(app_id: int, db: Session) -> List[RepositoryListItemSchema]:
        """
        Get list of repositories for an app - business logic from router
        
        Args:
            app_id: Application ID
            db: Database session
            
        Returns:
            List of RepositoryListItemSchema instances
        """
        logger.info(f"List repositories service called for app_id: {app_id}")
        
        # Use repository to get repositories
        repositories = RepositoryRepository.get_by_app_id(db, app_id)
        
        result = []
        for repo in repositories:
            resource_count = ResourceRepository.count_by_repository_id(db, repo.repository_id)
            
            if repo.silo and getattr(repo.silo, 'vector_db_type', None):
                repo_vector_db_type = repo.silo.vector_db_type
            else:
                default_type = config.VECTOR_DB_TYPE or 'PGVECTOR'
                repo_vector_db_type = default_type.upper() if isinstance(default_type, str) else default_type

            result.append(RepositoryListItemSchema(
                repository_id=repo.repository_id,
                name=repo.name,
                type=repo.type,
                status=repo.status,
                created_at=repo.create_date,
                resource_count=resource_count,
                vector_db_type=repo_vector_db_type
            ))
        
        return result

    @staticmethod
    def get_repository_detail(app_id: int, repository_id: int, db: Session) -> RepositoryDetailSchema:
        """
        Get detailed information about a repository - business logic from router
        
        Args:
            app_id: Application ID
            repository_id: Repository ID (0 for new repository)
            db: Database session
            
        Returns:
            RepositoryDetailSchema instance
            
        Raises:
            HTTPException: If repository not found
        """
        from fastapi import HTTPException, status
        
        if repository_id == 0:
            # New repository
            vector_db_options = VectorStoreFactory.get_available_type_options()
            embedding_services_query = EmbeddingServiceRepository.get_by_app_id(db, app_id)
            embedding_services = [{"service_id": s.service_id, "name": s.name} for s in embedding_services_query]
            return RepositoryDetailSchema(
                repository_id=0,
                name="",
                type=None,
                status=None,
                created_at=None,
                resources=[],
                embedding_services=[],
                silo_id=None,
                metadata_fields=[],
                vector_db_type=(config.VECTOR_DB_TYPE or 'PGVECTOR').upper(),
                vector_db_options=vector_db_options
            )
        
        # Existing repository
        repo = RepositoryRepository.get_by_id(db, repository_id)
        if not repo:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Repository not found"
            )
        
        # Get resources
        resources_query = ResourceRepository.get_by_repository_id(db, repository_id)
        resources = []
        for resource in resources_query:
            resources.append({
                "resource_id": resource.resource_id,
                "name": resource.name,
                "uri": resource.uri,
                "file_type": resource.type or "unknown",
                "created_at": resource.create_date,
                "folder_id": resource.folder_id
            })
        
        # Get embedding services for form data
        embedding_services_query = EmbeddingServiceRepository.get_by_app_id(db, app_id)
        embedding_services = [{"service_id": s.service_id, "name": s.name} for s in embedding_services_query]
        
        # Get folders for the repository
        from services.folder_service import FolderService
        folders_query = FolderService.get_all_folders_in_repository(repository_id, db)
        folders = [{"folder_id": f.folder_id, "name": f.name, "parent_folder_id": f.parent_folder_id} for f in folders_query]
        
        # Get the current embedding service ID from the repository's silo
        embedding_service_id = None
        silo_id = None
        metadata_fields = []
        
        if repo.silo:
            silo_id = repo.silo.silo_id
            if repo.silo.embedding_service:
                embedding_service_id = repo.silo.embedding_service.service_id
            
            # Get metadata fields from silo's metadata definition (OutputParser)
            if repo.silo.metadata_definition and repo.silo.metadata_definition.fields:
                try:
                    parser_fields = repo.silo.metadata_definition.fields
                    if isinstance(parser_fields, dict) and 'fields' in parser_fields:
                        for field_data in parser_fields['fields']:
                            if isinstance(field_data, dict):
                                metadata_fields.append({
                                    "name": field_data.get('name', ''),
                                    "type": field_data.get('type', 'string'),
                                    "description": field_data.get('description', '')
                                })
                except Exception as e:
                    logger.warning(f"Error parsing metadata fields for repository {repository_id}: {str(e)}")
        
        vector_db_options = VectorStoreFactory.get_available_type_options()
        if repo.silo and getattr(repo.silo, 'vector_db_type', None):
            vector_db_type = repo.silo.vector_db_type
        else:
            default_type = config.VECTOR_DB_TYPE or 'PGVECTOR'
            vector_db_type = default_type.upper() if isinstance(default_type, str) else default_type
        return RepositoryDetailSchema(
            repository_id=repo.repository_id,
            name=repo.name,
            type=repo.type,
            status=repo.status,
            created_at=repo.create_date,
            resources=resources,
            folders=folders,
            embedding_services=embedding_services,
            embedding_service_id=embedding_service_id,
            silo_id=silo_id,
            metadata_fields=metadata_fields,
            vector_db_type=vector_db_type,
            vector_db_options=vector_db_options
        )

    @staticmethod
    def create_or_update_repository_router(
        app_id: int, 
        repository_id: int, 
        repo_data: CreateUpdateRepositorySchema, 
        db: Session
    ) -> Repository:
        """
        Create or update a repository - business logic from router
        
        Args:
            app_id: Application ID
            repository_id: Repository ID (0 for new repository)
            repo_data: Repository data to create/update
            db: Database session
            
        Returns:
            Created or updated Repository instance
            
        Raises:
            HTTPException: If repository not found (for updates)
        """
        from fastapi import HTTPException, status

        normalized_vector_db_type = None
        if repo_data.vector_db_type is not None:
            if not isinstance(repo_data.vector_db_type, str):
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="vector_db_type must be a string"
                )
            candidate_type = repo_data.vector_db_type.strip().upper()
            if candidate_type and candidate_type not in VectorStoreFactory.IMPLEMENTED_TYPES:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=f"Unsupported vector_db_type '{candidate_type}'"
                )
            normalized_vector_db_type = candidate_type or None
        
        if repository_id == 0:
            # Create new repository
            repo = Repository()
            repo.app_id = app_id
            repo.name = repo_data.name
            repo.type = repo_data.type
            repo.status = repo_data.status or 'active'
            repo.create_date = datetime.now()
            
            # Use RepositoryService to create repository with silo
            repo = RepositoryService.create_repository(
                repo,
                repo_data.embedding_service_id,
                normalized_vector_db_type,
                db
            )
        else:
            # Update existing repository
            repo = RepositoryRepository.get_by_id(db, repository_id)
            if not repo:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Repository not found"
                )
            
            # Update repository data
            repo.name = repo_data.name
            if repo_data.type is not None:
                repo.type = repo_data.type
            if repo_data.status is not None:
                repo.status = repo_data.status
            repo = RepositoryService.update_repository(
                repo,
                repo_data.embedding_service_id,
                normalized_vector_db_type,
                db
            )
        
        return repo

    @staticmethod
    def delete_repository_router(repository_id: int, db: Session) -> bool:
        """
        Delete a repository using the router service layer
        
        Args:
            repository_id: Repository ID to delete
            db: Database session
            
        Returns:
            True if deletion was successful, False otherwise
        """
        repository = RepositoryRepository.get_by_id(db, repository_id)
        if not repository:
            return False
        
        try:
            RepositoryService.delete_repository(repository, db)
            return True
        except Exception as e:
            logger.error(f"Error deleting repository {repository_id}: {str(e)}")
            return False

    @staticmethod
    def search_repository_documents_router(
        repository_id: int,
        query: str,
        filter_metadata: Optional[Dict[str, Any]] = None,
        limit: int = 10,
        db: Session = None
    ) -> Dict[str, Any]:
        """
        Search documents in a repository by leveraging its associated silo
        
        Args:
            repository_id: Repository ID to search in
            query: Search query text
            filter_metadata: Optional metadata filters
            limit: Maximum number of results to return
            db: Database session
            
        Returns:
            Dictionary containing search results
            
        Raises:
            HTTPException: If repository or silo not found
        """
        # Get the repository
        repository = RepositoryRepository.get_by_id(db, repository_id)
        if not repository:
            from fastapi import HTTPException, status
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Repository {repository_id} not found"
            )
        
        # Check if repository has an associated silo
        if not repository.silo_id:
            from fastapi import HTTPException, status
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Repository {repository_id} has no associated silo for searching"
            )
        
        # Use SiloService to perform the search
        from services.silo_service import SiloService
        
        try:
            # Get the silo to validate it exists
            silo = SiloService.get_silo(repository.silo_id, db)
            if not silo:
                from fastapi import HTTPException, status
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Associated silo {repository.silo_id} not found"
                )
            
            # Perform the search using SiloService
            documents = SiloService.search_in_silo(
                silo_id=repository.silo_id,
                query=query,
                filter_metadata=filter_metadata,
                limit=limit,
                db=db
            )
            
            # Format results similar to silo search
            results = []
            for doc in documents:
                # Extract score from metadata if available
                score = doc.metadata.pop('_score', None) if '_score' in doc.metadata else None
                result = {
                    "page_content": doc.page_content,
                    "metadata": doc.metadata,
                    "score": score
                }
                results.append(result)
            
            return {
                "results": results,
                "total_count": len(results),
                "query": query,
                "repository_id": repository_id,
                "silo_id": repository.silo_id
            }
            
        except Exception as e:
            logger.error(f"Error searching repository {repository_id}: {str(e)}")
            from fastapi import HTTPException, status
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error searching repository: {str(e)}"
            ) 