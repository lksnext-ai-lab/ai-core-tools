import os
import warnings, deprecation

import numpy as np
from sqlalchemy.orm import sessionmaker

from langchain_openai import OpenAIEmbeddings
from langchain_community.document_loaders.pdf import PyPDFLoader
from langchain.text_splitter import CharacterTextSplitter
from langchain_postgres.vectorstores import PGVector
from langchain_community.embeddings import HuggingFaceEmbeddings
from model.embedding_service import EmbeddingProvider
from tools.embeddingTools import get_embeddings_model

from model.resource import Resource
from typing import Optional
from langchain.schema import Document
from typing import List
REPO_BASE_FOLDER = os.getenv("REPO_BASE_FOLDER")
#TODO: pgVector should not know abot silos
COLLECTION_PREFIX = 'silo_'

class PGVectorTools:
    def __init__(self, db):
        """Initializes the PGVectorTools with a SQLAlchemy engine."""
        self.Session = db.session
        self.db = db    

    @deprecation.deprecated(
        deprecated_in="0.1.0",
        current_version="0.1.0",
        details="This method is deprecated and will be removed in a future version. Use the 'index_documents' method instead."
    )
    def index_resource(self, resource):
        """Indexes a resource by loading its content, splitting it into chunks, and adding it to the pgvector table."""
        
        loader = PyPDFLoader(os.path.join(REPO_BASE_FOLDER, str(resource.repository_id), resource.uri), extract_images=False)
        pages = loader.load()
        text_splitter = CharacterTextSplitter(chunk_size=10, chunk_overlap=0)
        docs = text_splitter.split_documents(pages)

        for doc in docs:
            doc.metadata["repository_id"] = resource.repository_id
            doc.metadata["resource_id"] = resource.resource_id
            doc.metadata["silo_id"] = resource.repository.silo_id


        vector_store = PGVector(
            embeddings=get_embeddings_model(resource.embedding_service),
            collection_name=COLLECTION_PREFIX + str(resource.repository.silo_id),
            connection=self.db.engine,
            use_jsonb=True,
        )
        vector_store.add_documents(docs)

    def index_documents(self, collection_name: str, documents: list[Document], embedding_service=None):
        """Indexes a list of documents in the pgvector collection using langchain vector store."""
        vector_store = PGVector(
            embeddings=get_embeddings_model(embedding_service),
            collection_name=collection_name,
            connection=self.db.engine,
            use_jsonb=True,
        )
        vector_store.add_documents(documents)

    @deprecation.deprecated(
        deprecated_in="0.1.0",
        current_version="0.1.0",
        details="This method is deprecated and will be removed in a future version. Use the 'delete_documents' method instead."
    )
    def delete_resource(self, resource):
        """Deletes a resource from the pgvector table using langchain vector store."""
        vector_store = PGVector(
            embeddings=get_embeddings_model(resource.embedding_service),
            collection_name=COLLECTION_PREFIX + str(resource.repository.silo_id),
            connection=self.db.engine,
            use_jsonb=True,
        )
        results = vector_store.similarity_search(
            "", k=1000, filter={"resource_id": {"$eq": resource.resource_id}}
        )
        print(results)
        ids_array = [doc.id for doc in results]
        print(ids_array)
        
        vector_store.delete(ids=ids_array)

    def delete_documents(self, collection_name: str, ids, embedding_service=None):
        """Deletes documents from the pgvector collection using langchain vector store."""
        vector_store = PGVector(
            embeddings=get_embeddings_model(embedding_service),
            collection_name=collection_name,
            connection=self.db.engine,
            use_jsonb=True,
        )
        if isinstance(ids, list):
            vector_store.delete(ids=ids)
        else:
            results = vector_store.similarity_search(
                "", k=1000, filter=ids
            )
            ids_array = [doc.id for doc in results]
            vector_store.delete(ids=ids_array)

    def delete_collection(self, collection_name : str, embedding_service=None):
        """Deletes a collection from the pgvector database."""
        vector_store = PGVector(
            embeddings=get_embeddings_model(embedding_service),
            collection_name=collection_name,
            connection=self.db.engine,
        )
        vector_store.delete_collection()
        
    @deprecation.deprecated(
        deprecated_in="0.1.0",
        current_version="0.1.0",
        details="This method is deprecated and will be removed in a future version. Use the 'search_similar_documents' method instead."
    )
    def search_similar_resources(self, repository : str, embed, RESULTS=5):
        """Searches for similar resources in the pgvector table using langchain vector store."""
        vector_store = PGVector(
            embeddings=get_embeddings_model(None),
            collection_name=COLLECTION_PREFIX + str(repository.silo_id),
            connection=self.db.engine,
            use_jsonb=True,
        )
        results = vector_store.similarity_search_by_vector(
            embedding=embed,
            k=RESULTS
        )
        return results
    
    def search_similar_documents(self, collection_name: str, query: str, embedding_service=None, filter_metadata: Optional[dict] = None, RESULTS=5):
        """Searches for similar documents using the configured embedding service"""
        vector_store = PGVector(
            embeddings=get_embeddings_model(embedding_service),
            collection_name=collection_name,
            connection=self.db.engine,
            use_jsonb=True,
        )
        
        # Si recibimos directamente el embedding, lo usamos
        if isinstance(query, (list, np.ndarray)):
            results = vector_store.similarity_search_by_vector(
                embedding=query,
                k=RESULTS,
                filter=filter_metadata
            )
        else:
            # Si recibimos texto, hacemos la búsqueda normal
            results = vector_store.similarity_search(
                query,
                k=RESULTS,
                filter=filter_metadata
            )
        return results
    
    def get_pgvector_retriever(self, collection_name: str, embedding_service=None):
        """Returns a retriever object for the pgvector collection."""
        vector_store = PGVector(
            embeddings=get_embeddings_model(embedding_service),
            collection_name=collection_name,
            connection=self.db.engine,
            use_jsonb=True,
        )
        return vector_store.as_retriever()


