from typing import Optional, List
from model.silo import Silo
from model.output_parser import OutputParser
from extensions import db, engine
from sqlalchemy import text
from langchain_core.documents import Document
from langchain_text_splitters import CharacterTextSplitter
from langchain_community.document_loaders.pdf import PyPDFLoader
import time
from model.resource import Resource
from tools.pgVectorTools import PGVectorTools
import os
from model.silo import SiloType
from services.output_parser_service import OutputParserService
from langchain_core.vectorstores.base import VectorStoreRetriever
import logging

REPO_BASE_FOLDER = os.getenv("REPO_BASE_FOLDER")
COLLECTION_PREFIX = 'silo_'

logger = logging.getLogger(__name__)

class SiloService:


    '''SILO CRUD Operations'''
    @staticmethod
    def get_silo(silo_id: int) -> Optional[Silo]:
        """
        Retrieve a silo by its ID
        """
        return db.session.query(Silo).filter(Silo.silo_id == silo_id).first()
    
    @staticmethod
    def get_silo_retriever(silo_id: int) -> Optional[VectorStoreRetriever]:
        """
        Get retriever for a silo with its corresponding embedding service
        """
        silo = SiloService.get_silo(silo_id)
        if not silo:
            logger.error(f"Silo con id {silo_id} no existe")
            return None

        logger.debug(f"Obteniendo retriever para silo {silo_id} con embedding service: {silo.embedding_service.name if silo.embedding_service else 'None'}")
        
        pgVectorTools = PGVectorTools(db)
        collection_name = COLLECTION_PREFIX + str(silo_id)
        silo = SiloService.get_silo(silo_id)
        return pgVectorTools.get_pgvector_retriever(collection_name, silo.embedding_service)
    
    @staticmethod
    def get_silos_by_app_id(app_id: int) -> List[Silo]:
        """
        Retrieve all silos by app_id
        """
        return db.session.query(Silo).filter(Silo.app_id == app_id).all()
    
    @staticmethod
    def create_or_update_silo(silo_data: dict, silo_type: Optional[SiloType] = None) -> Silo:
        """
        Create a new silo or update an existing one
        """
        logger.info(f"Datos recibidos (silo_data): {silo_data}")
        
        silo_id = int(silo_data.get('silo_id'))
        
        silo = SiloService.get_silo(silo_id) if silo_id else None
        
        if not silo:    
            silo = Silo()
            silo.silo_type = SiloType.CUSTOM.value
        
        if silo_type:
            silo.silo_type = silo_type.value
        
        if silo_type == SiloType.REPO:
            silo.metadata_definition_id = 0

        if 'embedding_service_id' in silo_data and silo_data['embedding_service_id']:
            silo.embedding_service_id = int(silo_data['embedding_service_id'])
        
        SiloService._update_silo(silo, silo_data)
        
        try:
            db.session.add(silo)
            db.session.commit()
        except Exception as e:
            logger.error(f"Error al guardar el silo en la base de datos: {str(e)}")
            db.session.rollback()
            raise
        
        return silo
    
    @staticmethod
    def _update_silo(silo: Silo, data: dict):
        """
        Update silo attributes from input data
        """
        silo.name = data['name']
        silo.description = data.get('description')
        silo.status = data.get('status')
        silo.app_id = data['app_id']
        silo.fixed_metadata = data.get('fixed_metadata', False)
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
            SiloService.delete_collection(silo)
            
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
        #sql = text("SELECT COUNT(*) FROM langchain_pg_embedding WHERE cmetadata @> '{\"silo_id\": :silo_id}'::jsonb;")
        sql = text("SELECT COUNT(*) FROM langchain_pg_embedding WHERE collection_id = :collection_uuid;")
        result = db.session.execute(sql, {'collection_uuid': collection_uuid})
        return result.fetchone()[0]
    
    @staticmethod
    def index_content(silo_id: int, content: str, metadata: dict):
        """
        Index content in a silo with the corresponding embedding service
        """
        logger.info(f"Indexando contenido en silo {silo_id}")
        
        silo = SiloService.get_silo(silo_id)
        if not silo:
            logger.error(f"Silo con id {silo_id} no existe")
            raise ValueError(f"Silo with id {silo_id} does not exist")
        
        logger.debug(f"Usando embedding service: {silo.embedding_service.name if silo.embedding_service else 'None'}")
        
        collection_name = COLLECTION_PREFIX + str(silo_id)
        pgVectorTools = PGVectorTools(db)
        
        try:
            pgVectorTools.index_documents(
                collection_name, 
                [Document(page_content=content, metadata={"silo_id": silo_id, **metadata})],
                embedding_service=silo.embedding_service
            )
            logger.info(f"Contenido indexado correctamente en silo {silo_id}")
        except Exception as e:
            logger.error(f"Error al indexar contenido en silo {silo_id}: {str(e)}")
            raise

    @staticmethod
    def index_resource(resource: Resource):
        collection_name = COLLECTION_PREFIX + str(resource.repository.silo_id)
        loader = PyPDFLoader(os.path.join(REPO_BASE_FOLDER, str(resource.repository_id), resource.uri), extract_images=False)
        pages = loader.load()
        text_splitter = CharacterTextSplitter(chunk_size=10, chunk_overlap=0)
        docs = text_splitter.split_documents(pages)

        for doc in docs:
            doc.metadata["repository_id"] = resource.repository_id
            doc.metadata["resource_id"] = resource.resource_id
            doc.metadata["silo_id"] = resource.repository.silo_id

        pgVectorTools = PGVectorTools(db)
        embedding_service = resource.repository.silo.embedding_service
        pgVectorTools.index_documents(collection_name, docs, embedding_service)


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

        pgVectorTools = PGVectorTools(db)
        pgVectorTools.delete_documents(collection_name, ids={"resource_id": {"$eq": resource.resource_id}}, embedding_service=resource.repository.silo.embedding_service)

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
        pgVectorTools = PGVectorTools(db)
        pgVectorTools.delete_documents(
            collection_name, 
            filter_metadata={"id": {"$eq": content_id}},
            embedding_service=silo.embedding_service
        )
        logger.info(f"Contenido {content_id} eliminado correctamente del silo {silo_id}")

    @staticmethod
    def delete_collection(silo):
        if not SiloService.check_silo_collection_exists(silo.silo_id):
            return
        collection_name = COLLECTION_PREFIX + str(silo.silo_id)
        pgVectorTools = PGVectorTools(db)
        pgVectorTools.delete_collection(collection_name, silo.embedding_service)

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
        pgVectorTools = PGVectorTools(db)
        pgVectorTools.delete_documents(
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
        pgVectorTools = PGVectorTools(db)
        return pgVectorTools.search_similar_documents(
            collection_name, 
            query, 
            embedding_service=silo.embedding_service,
            filter_metadata=filter_metadata or {}
        )

    @staticmethod
    def get_metadata_filter_from_form(silo: Silo, form_data: dict) -> dict:
        filter_prefix = 'filter_'
        filter_dict = {}
        if not silo.metadata_definition:
            return filter_dict
        field_definitions = silo.metadata_definition.fields
        
        for field_name, field_value in form_data.items():
            if field_value and field_value != '':
                if field_name.startswith(filter_prefix):
                    name = field_name[len(filter_prefix):]
                    field_definition = next((f for f in field_definitions if f['name'] == name), None)
                    if field_definition:
                        if field_definition['type'] == 'str':
                            filter_dict[field_definition['name']] = {"$eq": f"{field_value}"}
                        elif field_definition['type'] == 'int':
                            filter_dict[field_definition['name']] = {"$eq": int(field_value)}
                        elif field_definition['type'] == 'bool':
                            filter_dict[field_definition['name']] = {"$eq": field_value}
                        elif field_definition['type'] == 'float':
                            filter_dict[field_definition['name']] = {"$eq": float(field_value)}
                        elif field_definition['type'] == 'date':
                            filter_dict[field_definition['name']] = {"$eq": field_value}
                
        return filter_dict