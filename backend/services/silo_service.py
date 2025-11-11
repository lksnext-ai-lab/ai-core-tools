from typing import Optional, List, Dict, Any
import os
import json
from models.silo import Silo
from models.resource import Resource
from db.database import SessionLocal
from sqlalchemy.orm import Session
from sqlalchemy import text
from utils.logger import get_logger
from langchain_core.documents import Document
from tools.pgVectorTools import PGVectorTools
from models.silo import SiloType
from services.output_parser_service import OutputParserService
from langchain_core.vectorstores.base import VectorStoreRetriever
from utils.error_handlers import (
    handle_database_errors, NotFoundError, ValidationError, 
    validate_required_fields
)
from schemas.silo_schemas import SiloListItemSchema, SiloDetailSchema, CreateUpdateSiloSchema
from repositories.silo_repository import SiloRepository

REPO_BASE_FOLDER = os.path.abspath(os.getenv("REPO_BASE_FOLDER"))
COLLECTION_PREFIX = 'silo_'

logger = get_logger(__name__)

class SiloService:

    '''SILO CRUD Operations'''
    @staticmethod
    def get_silo(silo_id: int, db: Session) -> Optional[Silo]:
        """
        Retrieve a silo by its ID
        """
        return SiloRepository.get_by_id(silo_id, db)
    
    @staticmethod
    def get_silo_retriever(silo_id: int, search_params=None, **kwargs) -> Optional[VectorStoreRetriever]:
        """
        Get retriever for a silo with its corresponding embedding service
        
        Args:
            silo_id: ID of the silo
            search_params: Optional search parameters for filtering
            
        Returns:
            VectorStoreRetriever if silo exists and has embedding service, None otherwise
            
        Raises:
            NotFoundError: If silo doesn't exist
            ValidationError: If silo has no embedding service
        """
        if not isinstance(silo_id, int) or silo_id <= 0:
            raise ValidationError(f"Invalid silo_id: {silo_id}")
        
        # For retriever operations, we need a fresh session since this might be called from other contexts
        session = SessionLocal()
        try:
            silo = SiloService.get_silo(silo_id, session)
            if not silo:
                raise NotFoundError(f"Silo with ID {silo_id} not found", "silo")

            if not silo.embedding_service:
                raise ValidationError(f"Silo {silo_id} has no embedding service configured")

            logger.debug(f"Getting retriever for silo {silo_id} with embedding service: {silo.embedding_service.name}")
            
            from db.database import db as db_obj  # Import the database object
            pg_vector_tools = PGVectorTools(db_obj)
            collection_name = COLLECTION_PREFIX + str(silo_id)
            
            # Merge search_params with default k value
            # search_params typically contains 'filter' for metadata filtering
            merged_search_kwargs = {'k': 30}
            
            if search_params:
                # Known retriever parameters that should not be wrapped in 'filter'
                known_params = {'k', 'filter', 'score_threshold', 'fetch_k', 'lambda_mult', 'search_type'}
                
                # Separate known params from filter fields
                filter_fields = {}
                direct_params = {}
                
                for key, value in search_params.items():
                    if key in known_params:
                        direct_params[key] = value
                    else:
                        # Any unknown key is treated as a filter field
                        filter_fields[key] = value
                
                # Update merged_search_kwargs with direct params
                merged_search_kwargs.update(direct_params)
                
                # If there are filter fields, wrap them in 'filter' key
                if filter_fields:
                    if 'filter' in merged_search_kwargs:
                        # Merge with existing filter
                        merged_search_kwargs['filter'].update(filter_fields)
                    else:
                        # Create new filter with these fields
                        merged_search_kwargs['filter'] = filter_fields
                
                logger.debug(f"Merged search_kwargs: {merged_search_kwargs}")
            
            # Use async engine with psycopg (not asyncpg) for async operations
            # psycopg supports async natively and handles multiple SQL statements properly
            return pg_vector_tools.get_pgvector_retriever(
                collection_name, 
                silo.embedding_service, 
                merged_search_kwargs,
                use_async=True  # Use async psycopg engine for LangGraph compatibility
            )
        except Exception as e:
            logger.error(f"Failed to create retriever for silo {silo_id}: {str(e)}", exc_info=True)
            raise
        finally:
            session.close()
    
    @staticmethod
    def get_silos_by_app_id(app_id: int, db: Session) -> List[Silo]:
        """
        Retrieve all silos by app_id
        """
        return SiloRepository.get_by_app_id(app_id, db)
    
    @staticmethod
    @handle_database_errors("create_or_update_silo")
    def create_or_update_silo(silo_data: dict, silo_type: Optional[SiloType] = None, db: Session = None) -> Silo:
        """
        Create a new silo or update an existing one
        
        Args:
            silo_data: Dictionary containing silo data
            silo_type: Optional silo type to set
            db: Database session to use
            
        Returns:
            Created or updated Silo instance
            
        Raises:
            ValidationError: If required fields are missing or invalid
            DatabaseError: If database operation fails
        """
        logger.info(f"Received silo data: {silo_data}")
        
        # Convert ImmutableMultiDict to regular dict if needed
        if hasattr(silo_data, 'to_dict'):
            silo_data = silo_data.to_dict()
        else:
            silo_data = dict(silo_data)
        
        # Validate required fields
        required_fields = ['name', 'app_id']
        validate_required_fields(silo_data, required_fields)
        
        # Validate field types
        field_types = {'app_id': int}
        if 'silo_id' in silo_data and silo_data['silo_id']:
            field_types['silo_id'] = int
        if 'embedding_service_id' in silo_data and silo_data['embedding_service_id']:
            field_types['embedding_service_id'] = int
        
        # Convert string values to int where needed
        for field in ['silo_id', 'app_id', 'embedding_service_id']:
            if field in silo_data and silo_data[field] and isinstance(silo_data[field], str):
                try:
                    silo_data[field] = int(silo_data[field])
                except ValueError:
                    raise ValidationError(f"Invalid integer value for {field}: {silo_data[field]}")
        
        silo_id = silo_data.get('silo_id')
        
        # Use provided session or create a new one
        session = db if db is not None else SessionLocal()
        should_close = db is None
        
        try:
            # Get existing silo or create new one
            if silo_id:
                silo = SiloService.get_silo(silo_id, session)
                if not silo:
                    raise NotFoundError(f"Silo with ID {silo_id} not found", "silo")
                logger.info(f"Updating existing silo {silo_id}")
            else:
                silo = Silo()
                # Set default type to CUSTOM, but allow override from form data
                silo.silo_type = SiloType.CUSTOM.value
                logger.info("Creating new silo")
            
            # Set silo type from form data if provided
            if silo_data.get('type') and silo_data['type'].strip():
                silo.silo_type = silo_data['type'].strip()
            # Set silo type if provided via parameter (for backward compatibility)
            elif silo_type:
                silo.silo_type = silo_type.value
                if silo_type == SiloType.REPO:
                    silo.metadata_definition_id = 0

            # Set embedding service if provided
            if silo_data.get('embedding_service_id'):
                silo.embedding_service_id = silo_data['embedding_service_id']
            
            # Handle metadata definition (output parser) - explicitly handle None to clear it
            if 'output_parser_id' in silo_data:
                # If output_parser_id is explicitly provided (even if None), use it
                logger.info(f"Setting metadata_definition_id to: {silo_data['output_parser_id']}")
                silo.metadata_definition_id = silo_data['output_parser_id']
            elif 'metadata_definition_id' in silo_data:
                # Fallback to metadata_definition_id for backward compatibility
                logger.info(f"Setting metadata_definition_id from fallback to: {silo_data['metadata_definition_id']}")
                silo.metadata_definition_id = silo_data['metadata_definition_id']
            
            # Update silo attributes
            SiloService._update_silo(silo, silo_data)
            
            # Save to database
            session.add(silo)
            session.commit()
            
            logger.info(f"Successfully {'updated' if silo_id else 'created'} silo {silo.silo_id}")
            return silo
        finally:
            if should_close:
                session.close()
    
    @staticmethod
    def _update_silo(silo: Silo, data: dict):
        """
        Update silo attributes from input data
        
        Args:
            silo: Silo instance to update
            data: Dictionary containing update data
            
        Raises:
            ValidationError: If data validation fails
        """
        # Validate silo name
        name = data['name'].strip() if data['name'] else None
        if not name:
            raise ValidationError("Silo name cannot be empty")
        
        silo.name = name
        silo.description = data.get('description', '').strip() or None
        silo.status = data.get('status')
        silo.app_id = data['app_id']
        silo.fixed_metadata = bool(data.get('fixed_metadata', False))
        # Don't override metadata_definition_id here as it's handled above
        # silo.metadata_definition_id = data.get('metadata_definition_id') or None
            
    @staticmethod
    def delete_silo(silo_id: int, db: Session):
        """
        Delete a silo by its ID
        """
        silo = SiloRepository.get_by_id(silo_id, db)
        if silo:
            # Store metadata_definition_id before deleting (avoid DetachedInstanceError)
            metadata_definition_id = silo.metadata_definition_id
            
            SiloService.delete_collection(silo.silo_id, db)
            
            silo.embedding_service_id = None
            db.add(silo)
            db.commit()
            
            # Now delete the silo using repository
            SiloRepository.delete(silo_id, db)

            # Finally delete the output parser if it exists
            if metadata_definition_id:
                output_parser_service = OutputParserService()
                output_parser_service.delete_parser(db, metadata_definition_id)



    '''SILO and DATA Operations'''

    @staticmethod
    def check_silo_collection_exists(silo_id: int, db: Session) -> bool:
        return SiloRepository.check_collection_exists(silo_id, db)
    
    @staticmethod
    def get_silo_collection_uuid(silo_id: int, db: Session) -> str:
        return SiloRepository.get_collection_uuid(silo_id, db)
    
    @staticmethod
    def count_docs_in_silo(silo_id: int, db: Session) -> int:
        if not SiloService.check_silo_collection_exists(silo_id, db):
            return 0
        collection_uuid = SiloService.get_silo_collection_uuid(silo_id, db)
        return SiloRepository.count_documents_in_collection(collection_uuid, db)
    
    @staticmethod
    def _get_silo_for_indexing(silo_id: int, db: Session):
        """Helper method to get silo and validate it exists"""
        silo = SiloService.get_silo(silo_id, db)
        if not silo:
            logger.error(f"Silo con id {silo_id} no existe")
            raise ValueError(f"Silo with id {silo_id} does not exist")
        return silo

    @staticmethod
    def _create_documents_for_indexing(silo_id: int, contents: List[dict]) -> List[Document]:
        """Helper method to create Document objects for indexing"""
        return [
            Document(
                page_content=doc['content'],
                metadata={"silo_id": silo_id, **(doc.get('metadata', {}))}
            )
            for doc in contents
        ]

    @staticmethod
    def index_single_content(silo_id: int, content: str, metadata: dict, db: Session):
        """Index single content in a silo"""
        SiloService.index_multiple_content(silo_id, [{'content': content, 'metadata': metadata}], db)

    @staticmethod
    def index_multiple_content(silo_id: int, documents: List[dict], db: Session):
        """Index multiple documents in a silo with the corresponding embedding service"""
        logger.info(f"Indexando documentos en silo {silo_id}")
        
        collection_name = COLLECTION_PREFIX + str(silo_id)
        
        # Get silo within this session to avoid detached instance
        silo = SiloRepository.get_by_id(silo_id, db)
        if not silo:
            logger.error(f"Silo con id {silo_id} no existe")
            raise ValueError(f"Silo with id {silo_id} does not exist")
        
        # Get embedding service within the same session
        embedding_service = None
        if silo.embedding_service_id:
            embedding_service = SiloRepository.get_embedding_service_by_id(silo.embedding_service_id, db)
        
        logger.debug(f"Usando embedding service: {embedding_service.name if embedding_service else 'None'}")
        
        from db.database import db as db_obj  # Import the database object
        pg_vector_tools = PGVectorTools(db_obj)
        docs = SiloService._create_documents_for_indexing(silo_id, documents)
        pg_vector_tools.index_documents(
            collection_name,
            docs,
            embedding_service=embedding_service
        )
        logger.info(f"Documentos indexados correctamente en silo {silo_id}")

    @staticmethod
    def extract_documents_from_file(file_path: str, file_extension: str, base_metadata: dict = None):
        """
        Extracts and splits documents from a file, attaching base metadata to each chunk.
        Args:
            file_path: Path to the file to extract from
            file_extension: File extension (e.g., '.pdf', '.docx', '.txt')
            base_metadata: Metadata dict to attach to each document
        Returns:
            List[Document]: List of Document objects
        """
        from langchain_core.documents import Document
        from langchain_text_splitters import CharacterTextSplitter
        from langchain_community.document_loaders.pdf import PyPDFLoader
        from langchain_community.document_loaders import Docx2txtLoader, TextLoader

        if base_metadata is None:
            base_metadata = {}

        # Determine file type and use appropriate loader
        if file_extension == '.pdf':
            loader = PyPDFLoader(file_path, extract_images=False)
        elif file_extension == '.docx':
            loader = Docx2txtLoader(file_path)
        elif file_extension == '.txt':
            loader = TextLoader(file_path, encoding='utf-8')
        else:
            logger.error(f"Unsupported file type: {file_extension}")
            raise ValueError(f"Unsupported file type: {file_extension}")

        pages = loader.load()
        text_splitter = CharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
        docs = text_splitter.split_documents(pages)

        for doc in docs:
            doc.metadata.update(base_metadata)
            # Only add page number if it exists (PDFs have page metadata, DOCX/TXT don't)
            if "page" in doc.metadata:
                doc.metadata["page"] = doc.metadata["page"] + 1
        return docs

    @staticmethod
    def update_resource_metadata(resource: Resource, db_session: Session = None):
        """
        Update only the metadata of a resource in the vector database without re-indexing content.
        This is more efficient for operations like moving files between folders.
        
        Args:
            resource: Resource instance with updated folder information
            db_session: Optional database session to use (if None, creates new session)
        """
        try:
            # Use provided session or create new one
            if db_session:
                session = db_session
            else:
                session = SessionLocal()
            
            # Get resource with relations
            resource_with_relations = session.query(Resource).filter(
                Resource.resource_id == resource.resource_id
            ).first()
            
            if not resource_with_relations:
                logger.error(f"Resource {resource.resource_id} not found for metadata update")
                return
            
            logger.info(f"Updating metadata for resource {resource.resource_id}, folder_id: {resource_with_relations.folder_id}")
            
            collection_name = COLLECTION_PREFIX + str(resource_with_relations.repository.silo_id)
            
            # Build the correct file path including folder structure
            if resource_with_relations.folder_id:
                from services.folder_service import FolderService
                folder_path = FolderService.get_folder_path(resource_with_relations.folder_id, session)
                path = os.path.join(REPO_BASE_FOLDER, str(resource_with_relations.repository_id), folder_path, resource_with_relations.uri)
            else:
                path = os.path.join(REPO_BASE_FOLDER, str(resource_with_relations.repository_id), resource_with_relations.uri)
            
            file_extension = os.path.splitext(resource_with_relations.uri)[1].lower()
            
            # Prepare updated metadata
            base_metadata = {
                "repository_id": resource_with_relations.repository_id,
                "resource_id": resource_with_relations.resource_id,
                "silo_id": resource_with_relations.repository.silo_id,
                "name": resource_with_relations.uri,
                "file_type": file_extension
            }
            
            # Add folder information if resource is in a folder
            if resource_with_relations.folder_id:
                from services.folder_service import FolderService
                folder_path = FolderService.get_folder_path(resource_with_relations.folder_id, session)
                base_metadata["folder_id"] = resource_with_relations.folder_id
                base_metadata["folder_path"] = folder_path
                # Store relative path including folder structure
                base_metadata["ref"] = os.path.join(str(resource_with_relations.repository_id), folder_path, resource_with_relations.uri)
                logger.info(f"Resource in folder: {folder_path}, ref: {base_metadata['ref']}")
            else:
                # Resource is at root level
                base_metadata["folder_id"] = None
                base_metadata["folder_path"] = ""
                base_metadata["ref"] = os.path.join(str(resource_with_relations.repository_id), resource_with_relations.uri)
                logger.info(f"Resource at root, ref: {base_metadata['ref']}")
            
            # Update metadata in vector database using direct SQL
            # The langchain_pg_embedding table stores documents with metadata as JSONB
            update_query = text("""
                UPDATE langchain_pg_embedding 
                SET cmetadata = :new_metadata
                WHERE collection_id = (
                    SELECT uuid FROM langchain_pg_collection WHERE name = :collection_name
                )
                AND cmetadata->>'resource_id' = :resource_id
            """)
            
            session.execute(update_query, {
                'new_metadata': json.dumps(base_metadata),
                'collection_name': collection_name,
                'resource_id': str(resource.resource_id)
            })
            session.commit()
            
            logger.info(f"Updated metadata for resource {resource.resource_id} in collection {collection_name}")
            
        except Exception as e:
            logger.error(f"Error updating resource metadata: {str(e)}")
            raise
        finally:
            # Only close if we created the session
            if not db_session:
                session.close()

    @staticmethod
    def index_resource(resource: Resource):
        # For resource operations, we need a fresh session since this might be called from other contexts
        session = SessionLocal()
        try:
            # Load resource with relationships within the session to avoid detached instance issues
            resource_with_relations = session.query(Resource).filter(Resource.resource_id == resource.resource_id).first()
            if not resource_with_relations:
                logger.error(f"Resource {resource.resource_id} not found for indexing")
                return
                
            collection_name = COLLECTION_PREFIX + str(resource_with_relations.repository.silo_id)
            
            # Build the correct file path including folder structure
            if resource_with_relations.folder_id:
                from services.folder_service import FolderService
                folder_path = FolderService.get_folder_path(resource_with_relations.folder_id, session)
                path = os.path.join(REPO_BASE_FOLDER, str(resource_with_relations.repository_id), folder_path, resource_with_relations.uri)
            else:
                path = os.path.join(REPO_BASE_FOLDER, str(resource_with_relations.repository_id), resource_with_relations.uri)
            
            file_extension = os.path.splitext(resource_with_relations.uri)[1].lower()

            # Prepare base metadata
            base_metadata = {
                "repository_id": resource_with_relations.repository_id,
                "resource_id": resource_with_relations.resource_id,
                "silo_id": resource_with_relations.repository.silo_id,
                "name": resource_with_relations.uri,
                "file_type": file_extension
            }
            
            # Add folder information if resource is in a folder
            if resource_with_relations.folder_id:
                from services.folder_service import FolderService
                folder_path = FolderService.get_folder_path(resource_with_relations.folder_id, session)
                base_metadata["folder_id"] = resource_with_relations.folder_id
                base_metadata["folder_path"] = folder_path
                # Store relative path including folder structure
                base_metadata["ref"] = os.path.join(str(resource_with_relations.repository_id), folder_path, resource_with_relations.uri)
            else:
                # Resource is at root level
                base_metadata["folder_id"] = None
                base_metadata["folder_path"] = ""
                base_metadata["ref"] = os.path.join(str(resource_with_relations.repository_id), resource_with_relations.uri)

            docs = SiloService.extract_documents_from_file(path, file_extension, base_metadata)

            from db.database import db as db_obj  # Import the database object
            pg_vector_tools = PGVectorTools(db_obj)
            embedding_service = resource_with_relations.repository.silo.embedding_service
            
            if not embedding_service:
                logger.warning(f"Silo {resource_with_relations.repository.silo_id} has no embedding service, skipping indexing for resource {resource_with_relations.resource_id}")
                return
                
            pg_vector_tools.index_documents(collection_name, docs, embedding_service)
            logger.info(f"Successfully indexed resource {resource_with_relations.resource_id} in silo {resource_with_relations.repository.silo_id}")
        except Exception as e:
            logger.error(f"Error indexing resource {resource.resource_id}: {str(e)}")
            raise
        finally:
            session.close()

    @staticmethod
    def delete_resource(resource: Resource):
        """
        Delete a resource using its silo's embedding service
        """
        logger.info(f"Eliminando recurso {resource.resource_id} del silo {resource.repository.silo_id}")
        collection_name = COLLECTION_PREFIX + str(resource.repository.silo_id)
        
        # For resource operations, we need a fresh session since this might be called from other contexts
        session = SessionLocal()
        try:
            # Load silo within the session to avoid detached instance issues
            silo = SiloRepository.get_by_id(resource.repository.silo_id, session)
            if not silo:
                logger.error(f"Silo no encontrado para el recurso {resource.resource_id}")
                return

            # Check if silo has embedding service
            if not silo.embedding_service:
                logger.warning(f"Silo {silo.silo_id} has no embedding service, skipping vector deletion for resource {resource.resource_id}")
                return

            from db.database import db as db_obj  # Import the database object
            pg_vector_tools = PGVectorTools(db_obj)
            pg_vector_tools.delete_documents(collection_name, ids={"resource_id": {"$eq": resource.resource_id}}, embedding_service=silo.embedding_service)
        except Exception as e:
            logger.error(f"Error deleting resource {resource.resource_id} from vector store: {str(e)}")
            # Don't raise the exception - allow the resource to be deleted from database and disk
        finally:
            session.close()

    @staticmethod
    def delete_url(silo_id: int, url: str, db: Session):
        """
        Delete a resource using its silo's embedding service
        """
        logger.info(f"Eliminando URL {url} del silo {silo_id}")
        collection_name = COLLECTION_PREFIX + str(silo_id)
        
        # Get silo within this session to avoid detached instance
        silo = SiloRepository.get_by_id(silo_id, db)
        if not silo:
            logger.error(f"Silo no encontrado para la url {url}")
            return

        from db.database import db as db_obj  # Import the database object
        pg_vector_tools = PGVectorTools(db_obj)
        
        # Get embedding service within the same session
        embedding_service = None
        if silo.embedding_service_id:
            embedding_service = SiloRepository.get_embedding_service_by_id(silo.embedding_service_id, db)
        
        pg_vector_tools.delete_documents(collection_name, ids={"url": {"$eq": url}}, embedding_service=embedding_service)
            
    @staticmethod
    def delete_content(silo_id: int, content_id: str, db: Session):
        """
        Delete content from a silo using its embedding service
        """
        logger.info(f"Eliminando contenido {content_id} del silo {silo_id}")
        
        if not SiloService.check_silo_collection_exists(silo_id, db):
            logger.warning(f"La colección para el silo {silo_id} no existe")
            return

        silo = SiloService.get_silo(silo_id, db)
        if not silo:
            logger.error(f"Silo {silo_id} no encontrado")
            return

        collection_name = COLLECTION_PREFIX + str(silo_id)
        from db.database import db as db_obj  # Import the database object
        pg_vector_tools = PGVectorTools(db_obj)
        pg_vector_tools.delete_documents(
            collection_name, 
            filter_metadata={"id": {"$eq": content_id}},
            embedding_service=silo.embedding_service
        )
        logger.info(f"Contenido {content_id} eliminado correctamente del silo {silo_id}")

    @staticmethod
    def delete_collection(silo_id: int, db: Session):
        """Delete a collection using its silo's embedding service"""
        if not SiloService.check_silo_collection_exists(silo_id, db):
            return
            
        # Get silo within the session to ensure relationships are loaded
        silo = SiloRepository.get_by_id(silo_id, db)
        if not silo:
            return
            
        collection_name = COLLECTION_PREFIX + str(silo_id)
        from db.database import db as db_obj  # Import the database object
        pg_vector_tools = PGVectorTools(db_obj)
        pg_vector_tools.delete_collection(collection_name, silo.embedding_service)

    @staticmethod
    def delete_docs_in_collection(silo_id: int, ids: List[str], db: Session):
        """
        Delete documents from a silo using its embedding service
        """
        logger.info(f"Eliminando documentos {ids} del silo {silo_id}")
        
        if not SiloService.check_silo_collection_exists(silo_id, db):
            logger.warning(f"La colección para el silo {silo_id} no existe")
            return

        # Get silo within the session to ensure relationships are loaded
        silo = SiloRepository.get_by_id(silo_id, db)
        if not silo:
            logger.error(f"Silo {silo_id} no encontrado")
            return

        collection_name = COLLECTION_PREFIX + str(silo_id)
        from db.database import db as db_obj  # Import the database object
        pg_vector_tools = PGVectorTools(db_obj)
        pg_vector_tools.delete_documents(
            collection_name, 
            ids=ids,
            embedding_service=silo.embedding_service
        )
        logger.info(f"Documentos eliminados correctamente del silo {silo_id}")

    @staticmethod
    def find_docs_in_collection(silo_id: int, query: str, filter_metadata: Optional[dict] = None, db: Session = None) -> List[Document]:
        # Get silo within the session to ensure relationships are loaded
        silo = SiloRepository.get_by_id(silo_id, db)
        if not silo or not SiloService.check_silo_collection_exists(silo_id, db):
            return []
        
        collection_name = COLLECTION_PREFIX + str(silo_id)
        from db.database import db as db_obj  # Import the database object
        pg_vector_tools = PGVectorTools(db_obj)
        
        # Get embedding service within the same session
        embedding_service = None
        if silo.embedding_service_id:
            embedding_service = SiloRepository.get_embedding_service_by_id(silo.embedding_service_id, db)
        
        return pg_vector_tools.search_similar_documents(
            collection_name, 
            query, 
            embedding_service=embedding_service,
            filter_metadata=filter_metadata or {}
        )

    @staticmethod
    def search_in_silo(silo_id: int, query: str, filter_metadata: Optional[dict] = None, limit: int = 10, db: Session = None) -> List[Document]:
        """
        Search for documents in a silo using semantic search
        
        Args:
            silo_id: ID of the silo to search in
            query: Search query text
            filter_metadata: Optional metadata filters
            limit: Maximum number of results to return
            db: Database session
            
        Returns:
            List of Document objects with page_content and metadata
        """
        # Use find_docs_in_collection as the base implementation
        results = SiloService.find_docs_in_collection(silo_id, query, filter_metadata, db)
        
        # Apply limit if specified
        if limit and limit > 0:
            results = results[:limit]
            
        return results

    @staticmethod
    def _get_filter_value_by_type(field_value: str, field_type: str) -> dict:
        """Helper method to convert field value to the appropriate type for filtering"""
        if field_type == 'int':
            return {"$eq": int(field_value)}
        elif field_type == 'float':
            return {"$eq": float(field_value)}
        elif field_type == 'bool':
            return {"$eq": field_value}
        elif field_type in ['str', 'date']:
            return {"$eq": field_value}
        return {"$eq": field_value}  # default case

    @staticmethod
    def get_metadata_filter_from_form(silo: Silo, form_data: dict) -> dict:
        filter_dict = {}
        if not silo.metadata_definition:
            return filter_dict

        field_definitions = {f['name']: f for f in silo.metadata_definition.fields}
        filter_prefix = 'filter_'
        
        for field_name, field_value in form_data.items():
            if not field_value or field_value == '':
                continue
                
            if not field_name.startswith(filter_prefix):
                continue
                
            name = field_name[len(filter_prefix):]
            if name not in field_definitions:
                continue
                
            field_definition = field_definitions[name]
            filter_dict[name] = SiloService._get_filter_value_by_type(
                field_value, 
                field_definition['type']
            )
        
        return filter_dict 

    # ==================== ROUTER SERVICE METHODS ====================
    
    @staticmethod
    def get_silos_list(app_id: int, db: Session) -> List[SiloListItemSchema]:
        """
        Get list of silos for a specific app with document counts
        """
        # Get silos using the existing service
        silos = SiloService.get_silos_by_app_id(app_id, db)
        
        result = []
        for silo in silos:
            # Get document count
            docs_count = SiloService.count_docs_in_silo(silo.silo_id, db)
            
            result.append(SiloListItemSchema(
                silo_id=silo.silo_id,
                name=silo.name,
                description=silo.description,
                type=silo.silo_type if silo.silo_type else None,
                created_at=silo.create_date,
                docs_count=docs_count
            ))
        
        return result
    
    @staticmethod
    def get_silo_detail(app_id: int, silo_id: int, db: Session) -> SiloDetailSchema:
        """
        Get detailed silo information including form data for editing
        """
        logger.info(f"Getting silo detail for app_id: {app_id}, silo_id: {silo_id}")
        
        if silo_id == 0:
            # New silo
            logger.info("Returning new silo template")
            return SiloDetailSchema(
                silo_id=0,
                name="",
                description=None,
                type=None,
                created_at=None,
                docs_count=0,
                # Form data
                output_parsers=[],
                embedding_services=[]
            )
        
        # Existing silo
        logger.info(f"Getting existing silo {silo_id}")
        silo = SiloService.get_silo(silo_id, db)
        if not silo:
            logger.error(f"Silo {silo_id} not found")
            return None
        
        logger.info(f"Found silo: {silo.name}, app_id: {silo.app_id}")
        
        # Get document count
        try:
            logger.info(f"Counting docs in silo {silo_id}")
            docs_count = SiloService.count_docs_in_silo(silo_id, db)
            logger.info(f"Docs count: {docs_count}")
        except Exception as e:
            logger.error(f"Error counting docs in silo {silo_id}: {str(e)}")
            docs_count = 0
        
        # Get form data using repository consolidation
        try:
            logger.info(f"Getting form data for app_id: {app_id}")
            form_data = SiloRepository.get_form_data_for_silo(app_id, 0, db)  # We already have the silo
            output_parsers = [{"parser_id": p.parser_id, "name": p.name} for p in form_data['output_parsers']]
            embedding_services = [{"service_id": s.service_id, "name": s.name} for s in form_data['embedding_services']]
            logger.info(f"Found {len(output_parsers)} parsers and {len(embedding_services)} embedding services")
        except Exception as e:
            logger.error(f"Error getting form data: {str(e)}")
            output_parsers = []
            embedding_services = []
        
        # Get metadata definition fields if silo has one
        metadata_fields = None
        try:
            if silo.metadata_definition_id:
                logger.info(f"Getting metadata parser {silo.metadata_definition_id}")
                metadata_parser = SiloRepository.get_output_parser_by_id(silo.metadata_definition_id, db)
                if metadata_parser and metadata_parser.fields:
                    metadata_fields = [
                        {
                            "name": field.get("name", ""),
                            "type": field.get("type", "str"),
                            "description": field.get("description", "")
                        }
                        for field in metadata_parser.fields
                    ]
        except Exception as e:
            logger.error(f"Error getting metadata fields: {str(e)}")
            metadata_fields = None
        
        try:
            logger.info(f"Creating SiloDetailSchema for silo {silo_id}")
            return SiloDetailSchema(
                silo_id=silo.silo_id,
                name=silo.name,
                description=silo.description,
                type=silo.silo_type if silo.silo_type else None,
                created_at=silo.create_date,
                docs_count=docs_count,
                # Current values for editing
                metadata_definition_id=silo.metadata_definition_id,
                embedding_service_id=silo.embedding_service_id,
                # Form data
                output_parsers=output_parsers,
                embedding_services=embedding_services,
                # Metadata definition fields for playground
                metadata_fields=metadata_fields
            )
        except Exception as e:
            logger.error(f"Error creating SiloDetailSchema: {str(e)}")
            raise
    
    @staticmethod
    def create_or_update_silo_router(
        app_id: int, 
        silo_id: int, 
        silo_data: CreateUpdateSiloSchema, 
        db: Session
    ) -> Silo:
        """
        Create or update silo using router data
        """
        # Prepare form data for the service
        form_data = {
            'silo_id': silo_id,
            'name': silo_data.name,
            'description': silo_data.description,
            'app_id': app_id,
            'type': silo_data.type,
            'output_parser_id': silo_data.output_parser_id,
            'embedding_service_id': silo_data.embedding_service_id
        }
        
        # Create or update using the existing service
        silo = SiloService.create_or_update_silo(form_data, db=db)
        return silo
    
    @staticmethod
    def delete_silo_router(silo_id: int, db: Session) -> bool:
        """
        Delete a silo and all its documents
        """
        return SiloRepository.delete(silo_id, db)
    
    @staticmethod
    def get_silo_playground_info(silo_id: int, db: Session) -> Optional[Dict[str, Any]]:
        """
        Get silo playground information
        """
        # Get silo info
        silo = SiloService.get_silo(silo_id, db)
        if not silo:
            return None
        
        docs_count = SiloService.count_docs_in_silo(silo_id, db)
        
        return {
            "silo_id": silo.silo_id,
            "name": silo.name,
            "docs_count": docs_count,
            "message": "Silo playground - ready for document search testing"
        }
    
    @staticmethod
    def search_silo_documents_router(
        silo_id: int, 
        query: str, 
        filter_metadata: Optional[Dict[str, Any]] = None,
        db: Session = None
    ) -> Optional[Dict[str, Any]]:
        """
        Search for documents in a silo using semantic search with optional metadata filtering
        """
        # Get silo to validate it exists
        silo = SiloService.get_silo(silo_id, db)
        if not silo:
            return None
        
        # Perform the search with metadata filtering
        results = SiloService.find_docs_in_collection(
            silo_id, 
            query, 
            filter_metadata=filter_metadata,
            db=db
        )
        
        # Convert results to response format
        response_results = []
        for doc in results:
            # Extract score from metadata if available
            score = doc.metadata.pop('_score', None) if '_score' in doc.metadata else None
            response_results.append({
                "page_content": doc.page_content,
                "metadata": doc.metadata,
                "score": score
            })
        
        return {
            "query": query,
            "results": response_results,
            "total_results": len(response_results),
            "filter_metadata": filter_metadata
        }