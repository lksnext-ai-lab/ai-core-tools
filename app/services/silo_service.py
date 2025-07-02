from typing import Optional, List, Dict, Any
from model.silo import Silo
from model.output_parser import OutputParser
from extensions import db, engine
from sqlalchemy import text
from langchain_core.documents import Document
from langchain_text_splitters import CharacterTextSplitter
from langchain_community.document_loaders.pdf import PyPDFLoader
from langchain_community.document_loaders import Docx2txtLoader, TextLoader
import time
from model.resource import Resource
from tools.pgVectorTools import PGVectorTools
import os
from model.silo import SiloType
from services.output_parser_service import OutputParserService
from langchain_core.vectorstores.base import VectorStoreRetriever
from utils.logger import get_logger
from utils.error_handlers import (
    handle_database_errors, NotFoundError, ValidationError, 
    validate_required_fields, safe_execute
)

REPO_BASE_FOLDER = os.path.abspath(os.getenv("REPO_BASE_FOLDER"))
COLLECTION_PREFIX = 'silo_'

logger = get_logger(__name__)

class SiloService:


    '''SILO CRUD Operations'''
    @staticmethod
    def get_silo(silo_id: int) -> Optional[Silo]:
        """
        Retrieve a silo by its ID
        """
        return db.session.query(Silo).filter(Silo.silo_id == silo_id).first()
    
    @staticmethod
    def get_silo_retriever(silo_id: int, search_params=None) -> Optional[VectorStoreRetriever]:
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
        
        silo = SiloService.get_silo(silo_id)
        if not silo:
            raise NotFoundError(f"Silo with ID {silo_id} not found", "silo")

        if not silo.embedding_service:
            raise ValidationError(f"Silo {silo_id} has no embedding service configured")

        logger.debug(f"Getting retriever for silo {silo_id} with embedding service: {silo.embedding_service.name}")
        
        try:
            pg_vector_tools = PGVectorTools(db)
            collection_name = COLLECTION_PREFIX + str(silo_id)
            return pg_vector_tools.get_pgvector_retriever(collection_name, silo.embedding_service, search_params)
        except Exception as e:
            logger.error(f"Failed to create retriever for silo {silo_id}: {str(e)}", exc_info=True)
            raise
    
    @staticmethod
    def get_silos_by_app_id(app_id: int) -> List[Silo]:
        """
        Retrieve all silos by app_id
        """
        return db.session.query(Silo).filter(Silo.app_id == app_id).all()
    
    @staticmethod
    @handle_database_errors("create_or_update_silo")
    def create_or_update_silo(silo_data: dict, silo_type: Optional[SiloType] = None) -> Silo:
        """
        Create a new silo or update an existing one
        
        Args:
            silo_data: Dictionary containing silo data
            silo_type: Optional silo type to set
            
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
            # Create a mutable copy if it's any other immutable type
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
        
        # Get existing silo or create new one
        if silo_id:
            silo = SiloService.get_silo(silo_id)
            if not silo:
                raise NotFoundError(f"Silo with ID {silo_id} not found", "silo")
            logger.info(f"Updating existing silo {silo_id}")
        else:
            silo = Silo()
            silo.silo_type = SiloType.CUSTOM.value
            logger.info("Creating new silo")
        
        # Set silo type if provided
        if silo_type:
            silo.silo_type = silo_type.value
            if silo_type == SiloType.REPO:
                silo.metadata_definition_id = 0

        # Set embedding service if provided
        if silo_data.get('embedding_service_id'):
            silo.embedding_service_id = silo_data['embedding_service_id']
        
        # Update silo attributes
        SiloService._update_silo(silo, silo_data)
        
        # Save to database
        db.session.add(silo)
        db.session.commit()
        
        logger.info(f"Successfully {'updated' if silo_id else 'created'} silo {silo.silo_id}")
        return silo
    
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
        silo.metadata_definition_id = data.get('metadata_definition_id') or None
    
    @staticmethod
    def get_silo_form_data(app_id: int, silo_id: int) -> dict:
        """
        Get data needed for rendering the silo form
        
        Args:
            app_id: ID of the application
            silo_id: ID of the silo to edit (0 for new silo)
            
        Returns:
            Dictionary with form data
        """
        output_parsers = db.session.query(OutputParser).filter(OutputParser.app_id == app_id).all()
        
        if silo_id == 0:
            return {
                'app_id': app_id,
                'silo': Silo(silo_id=0, name=""),
                'output_parsers': output_parsers
            }
        
        silo = db.session.query(Silo).filter(Silo.silo_id == silo_id).first()
        return {
            'app_id': app_id,
            'silo': silo,
            'output_parsers': output_parsers
        }
    
    @staticmethod
    def delete_silo(silo_id: int):
        """
        Delete a silo by its ID
        """
        silo = db.session.query(Silo).filter(Silo.silo_id == silo_id).first()
        if silo:
            SiloService.delete_collection(silo.silo_id)
            
            silo.embedding_service_id = None
            db.session.add(silo)
            db.session.commit()
            
            # Now delete the silo
            db.session.delete(silo)
            db.session.commit()

            # Finally delete the output parser if it exists
            output_parser_service = OutputParserService()
            if silo.metadata_definition_id:
                output_parser_service.delete_parser(silo.metadata_definition_id)

    '''SILO and DATA Operations'''

    @staticmethod
    def check_silo_collection_exists(silo_id: int) -> bool:
        sql = text("SELECT COUNT(*) FROM langchain_pg_collection WHERE name = :silo_id;")
        result = db.session.execute(sql, {'silo_id': 'silo_' + str(silo_id)})
        return result.fetchone()[0] > 0
    
    @staticmethod
    def get_silo_collection_uuid(silo_id: int) -> str:
        sql = text("SELECT uuid FROM langchain_pg_collection WHERE name = :silo_id;")
        result = db.session.execute(sql, {'silo_id': 'silo_' + str(silo_id)})
        return result.fetchone()[0]
    
    @staticmethod
    def count_docs_in_silo(silo_id: int) -> int:
        if not SiloService.check_silo_collection_exists(silo_id):
            return 0
        collection_uuid = SiloService.get_silo_collection_uuid(silo_id)
        sql = text("SELECT COUNT(*) FROM langchain_pg_embedding WHERE collection_id = :collection_uuid;")
        result = db.session.execute(sql, {'collection_uuid': collection_uuid})
        return result.fetchone()[0]
    
    @staticmethod
    def _get_silo_for_indexing(silo_id: int):
        """Helper method to get silo and validate it exists"""
        silo = SiloService.get_silo(silo_id)
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
    def index_single_content(silo_id: int, content: str, metadata: dict):
        """Index single content in a silo"""
        SiloService.index_multiple_content(silo_id, [{'content': content, 'metadata': metadata}])

    @staticmethod
    def index_multiple_content(silo_id: int, documents: List[dict]):
        """Index multiple documents in a silo with the corresponding embedding service"""
        logger.info(f"Indexando documentos en silo {silo_id}")
        
        silo = SiloService._get_silo_for_indexing(silo_id)
        logger.debug(f"Usando embedding service: {silo.embedding_service.name if silo.embedding_service else 'None'}")
        
        collection_name = COLLECTION_PREFIX + str(silo_id)
        pg_vector_tools = PGVectorTools(db)
        
        try:
            docs = SiloService._create_documents_for_indexing(silo_id, documents)
            pg_vector_tools.index_documents(
                collection_name,
                docs,
                embedding_service=silo.embedding_service
            )
            logger.info(f"Documentos indexados correctamente en silo {silo_id}")
        except Exception as e:
            logger.error(f"Error al indexar documentos en silo {silo_id}: {str(e)}")
            raise

    @staticmethod
    def index_resource(resource: Resource):
        collection_name = COLLECTION_PREFIX + str(resource.repository.silo_id)
        path = os.path.join(REPO_BASE_FOLDER, str(resource.repository_id), resource.uri)
        
        # Determine file type and use appropriate loader
        file_extension = os.path.splitext(resource.uri)[1].lower()
        
        if file_extension == '.pdf':
            loader = PyPDFLoader(path, extract_images=False)
        elif file_extension == '.docx':
            loader = Docx2txtLoader(path)
        elif file_extension == '.txt':
            loader = TextLoader(path, encoding='utf-8')
        else:
            logger.error(f"Unsupported file type: {file_extension}")
            raise ValueError(f"Unsupported file type: {file_extension}")
        
        pages = loader.load()
        text_splitter = CharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
        docs = text_splitter.split_documents(pages)

        #TODO: add metadata to the document according to the silo metadata definition
        for doc in docs:
            doc.metadata["repository_id"] = resource.repository_id
            doc.metadata["resource_id"] = resource.resource_id
            doc.metadata["silo_id"] = resource.repository.silo_id
            doc.metadata["name"] = resource.uri
            # Store relative path instead of absolute path for portability
            doc.metadata["ref"] = os.path.join(str(resource.repository_id), resource.uri)
            doc.metadata["file_type"] = file_extension

        pg_vector_tools = PGVectorTools(db)
        embedding_service = resource.repository.silo.embedding_service
        pg_vector_tools.index_documents(collection_name, docs, embedding_service)


    @staticmethod
    def delete_resource(resource: Resource):
        """
        Delete a resource using its silo's embedding service
        """
        logger.info(f"Eliminando recurso {resource.resource_id} del silo {resource.repository.silo_id}")
        collection_name = COLLECTION_PREFIX + str(resource.repository.silo_id)
        
        silo = SiloService.get_silo(resource.repository.silo_id)
        if not silo:
            logger.error(f"Silo no encontrado para el recurso {resource.resource_id}")
            return

        pg_vector_tools = PGVectorTools(db)
        pg_vector_tools.delete_documents(collection_name, ids={"resource_id": {"$eq": resource.resource_id}}, embedding_service=resource.repository.silo.embedding_service)

    @staticmethod
    def delete_url(silo_id: int, url: str):
        """
        Delete a resource using its silo's embedding service
        """
        logger.info(f"Eliminando URL {url} del silo {silo_id}")
        collection_name = COLLECTION_PREFIX + str(silo_id)
        
        silo = SiloService.get_silo(silo_id= silo_id)
        if not silo:
            logger.error(f"Silo no encontrado para la url {url}")
            return

        pg_vector_tools = PGVectorTools(db)
        pg_vector_tools.delete_documents(collection_name, ids={"url": {"$eq": url}}, embedding_service=silo.embedding_service)
    @staticmethod
    def delete_content(silo_id: int, content_id: str):
        """
        Delete content from a silo using its embedding service
        """
        logger.info(f"Eliminando contenido {content_id} del silo {silo_id}")
        
        if not SiloService.check_silo_collection_exists(silo_id):
            logger.warning(f"La colección para el silo {silo_id} no existe")
            return

        silo = SiloService.get_silo(silo_id)
        if not silo:
            logger.error(f"Silo {silo_id} no encontrado")
            return

        collection_name = COLLECTION_PREFIX + str(silo_id)
        pg_vector_tools = PGVectorTools(db)
        pg_vector_tools.delete_documents(
            collection_name, 
            filter_metadata={"id": {"$eq": content_id}},
            embedding_service=silo.embedding_service
        )
        logger.info(f"Contenido {content_id} eliminado correctamente del silo {silo_id}")

    @staticmethod
    def delete_collection(silo_id: int):
        """Delete a collection using its silo's embedding service"""
        if not SiloService.check_silo_collection_exists(silo_id):
            return
            
        silo = SiloService.get_silo(silo_id)
        if not silo:
            return
            
        collection_name = COLLECTION_PREFIX + str(silo_id)
        pg_vector_tools = PGVectorTools(db)
        pg_vector_tools.delete_collection(collection_name, silo.embedding_service)

    @staticmethod
    def delete_docs_in_collection(silo_id: int, ids: List[str]):
        """
        Delete documents from a silo using its embedding service
        """
        logger.info(f"Eliminando documentos {ids} del silo {silo_id}")
        
        if not SiloService.check_silo_collection_exists(silo_id):
            logger.warning(f"La colección para el silo {silo_id} no existe")
            return

        silo = SiloService.get_silo(silo_id)
        if not silo:
            logger.error(f"Silo {silo_id} no encontrado")
            return

        collection_name = COLLECTION_PREFIX + str(silo_id)
        pg_vector_tools = PGVectorTools(db)
        pg_vector_tools.delete_documents(
            collection_name, 
            ids=ids,
            embedding_service=silo.embedding_service
        )
        logger.info(f"Documentos eliminados correctamente del silo {silo_id}")

    @staticmethod
    def find_docs_in_collection(silo_id: int, query: str, filter_metadata: Optional[dict] = None) -> List[Document]:
        silo = SiloService.get_silo(silo_id)
        if not silo or not SiloService.check_silo_collection_exists(silo_id):
            return []
        
        collection_name = COLLECTION_PREFIX + str(silo_id)
        pg_vector_tools = PGVectorTools(db)
        return pg_vector_tools.search_similar_documents(
            collection_name, 
            query, 
            embedding_service=silo.embedding_service,
            filter_metadata=filter_metadata or {}
        )

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