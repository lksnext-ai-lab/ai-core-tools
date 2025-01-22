from typing import Optional, List
from app.model.silo import Silo
from app.model.output_parser import OutputParser
from app.extensions import db, engine
from sqlalchemy import text
from langchain_postgres import PGVector
from langchain_core.documents import Document
from langchain_openai import OpenAIEmbeddings
import time

class SiloService:

    embeddings = OpenAIEmbeddings(model="text-embedding-3-large")


    '''SILO CRUD Operations'''
    @staticmethod
    def get_silo(silo_id: int) -> Optional[Silo]:
        """
        Retrieve a silo by its ID
        """
        return db.session.query(Silo).filter(Silo.silo_id == silo_id).first()
    
    @staticmethod
    def get_silos_by_app_id(app_id: int) -> List[Silo]:
        """
        Retrieve all silos by app_id
        """
        return db.session.query(Silo).filter(Silo.app_id == app_id).all()
    
    @staticmethod
    def create_or_update_silo(silo_data: dict) -> Silo:
        """
        Create a new silo or update an existing one
        """
        silo_id = int(silo_data.get('silo_id'))
        silo = SiloService.get_silo(silo_id) if silo_id else None
        
        if not silo:
            silo = Silo()
            
        SiloService._update_silo(silo, silo_data)
        db.session.add(silo)
        db.session.commit()
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
            db.session.delete(silo)
            db.session.commit()

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
        silo = SiloService.get_silo(silo_id)
        if not silo:
            raise ValueError(f"Silo with id {silo_id} does not exist")
        
        #if not SiloService.check_silo_collection_exists(silo_id):
        #    raise ValueError(f"Silo collection for silo_id {silo_id} does not exist")

        
        collection_name = 'silo_' + str(silo_id)
        vector_store = PGVector(
            embeddings=SiloService.embeddings,
            collection_name=collection_name,
            connection=engine,
            use_jsonb=True,

        )
        documents = [Document(page_content=content, metadata={"silo_id": silo_id, **metadata})]
        vector_store.add_documents(documents)

    @staticmethod
    def delete_collection(silo_id: int):
        if not SiloService.check_silo_collection_exists(silo_id):
            return
        collection_name = 'silo_' + str(silo_id)
        vector_store = PGVector(
            embeddings=SiloService.embeddings,
            collection_name=collection_name,
            connection=engine,
        )
        vector_store.delete()

    @staticmethod
    def delete_docs_in_collection(silo_id: int, ids: List[str]):
        if not SiloService.check_silo_collection_exists(silo_id):
            return
        collection_name = 'silo_' + str(silo_id)
        vector_store = PGVector(
            embeddings=SiloService.embeddings,
            collection_name=collection_name,
            connection=engine,
        )
        vector_store.delete(ids=ids, collection_only=True)

    @staticmethod
    def find_docs_in_collection(silo_id: int, query: str, filter_metadata: dict) -> List[Document]:
        if not SiloService.check_silo_collection_exists(silo_id):
            return []
        collection_name = 'silo_' + str(silo_id)
        vector_store = PGVector(
            embeddings=SiloService.embeddings,
            collection_name=collection_name,
            connection=engine,
        )
        return vector_store.similarity_search(query, filter=filter_metadata)


