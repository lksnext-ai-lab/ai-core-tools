from langchain_openai import OpenAIEmbeddings
from langchain_community.document_loaders.pdf import PyPDFLoader
from langchain.text_splitter import CharacterTextSplitter
from langchain_postgres import PGVector
from langchain_postgres.vectorstores import PGVector
from app.model.resource import Resource
import os
import numpy as np
from sqlalchemy.orm import sessionmaker

REPO_BASE_FOLDER = os.getenv("REPO_BASE_FOLDER")
COLLECTION_PREFIX = 'collection_'

class PGVectorTools:
    def __init__(self, db):
        """Initializes the PGVectorTools with a SQLAlchemy engine."""
        self.Session = db.session
        self.db = db    

    def create_pgvector_table(self, repository_id):
        """Creates a pgvector table for the given repository if it doesn't exist."""
        table_name = COLLECTION_PREFIX + str(repository_id)
        session = self.Session()
        try:
            session.execute(f"""
                CREATE TABLE IF NOT EXISTS {table_name} (
                    id SERIAL PRIMARY KEY,
                    source TEXT,
                    embedding VECTOR(1536) -- Adjust the vector size according to the embedding model
                );
            """)
            session.commit()
        finally:
            session.close()

    def index_resource(self, resource):
        """Indexes a resource by loading its content, splitting it into chunks, and adding it to the pgvector table."""
        loader = PyPDFLoader(os.path.join(REPO_BASE_FOLDER, str(resource.repository_id), resource.uri), extract_images=False)
        pages = loader.load()
        text_splitter = CharacterTextSplitter(chunk_size=10, chunk_overlap=0)
        docs = text_splitter.split_documents(pages)

        vector_store = PGVector(
            embeddings=OpenAIEmbeddings(),
            collection_name=COLLECTION_PREFIX + str(resource.repository_id),
            connection=self.db.engine,
            use_jsonb=True,
        )
        vector_store.add_documents(docs)

    def delete_resource(self, resource):
        """Deletes a resource from the pgvector table using langchain vector store."""
        vector_store = PGVector(
            embeddings=OpenAIEmbeddings(),
            collection_name=COLLECTION_PREFIX + str(resource.repository_id),
            connection=self.db.engine,
            use_jsonb=True,
        )
        results = vector_store.similarity_search(
            "", k=1000, filter={"source": {"$eq": f"{REPO_BASE_FOLDER}/{resource.repository_id}/{resource.uri}"}}
        )
        print(results)
        ids_array = [doc.id for doc in results]
        print(ids_array)
        
        vector_store.delete(ids=ids_array)
        
        

    def search_similar_resources(self, repository_id, embed, RESULTS=5):
        """Searches for similar resources in the pgvector table using langchain vector store."""
        vector_store = PGVector(
            embeddings=OpenAIEmbeddings(),
            collection_name=COLLECTION_PREFIX + str(repository_id),
            connection=self.db.engine,
            use_jsonb=True,
        )
        results = vector_store.similarity_search_by_vector(
            embedding=embed,
            k=RESULTS
        )
        return results

    def get_pgvector_retriever(self, repository_id):
        """Returns a retriever object for the pgvector collection."""
        vector_store = PGVector(
            embeddings=OpenAIEmbeddings(),
            collection_name=COLLECTION_PREFIX + str(repository_id),
            connection=self.db.engine,
            use_jsonb=True,
        )
        retriever = vector_store.as_retriever()
        return retriever

# Usage example:
# from sqlalchemy import create_engine
# engine = create_engine('postgresql://user:password@localhost/dbname')
# pg_vector_tools = PGVectorTools(engine)
