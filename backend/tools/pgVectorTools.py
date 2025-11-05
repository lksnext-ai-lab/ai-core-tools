import os
import warnings
import deprecation

import numpy as np
from sqlalchemy.orm import sessionmaker

from langchain_openai import OpenAIEmbeddings
from langchain_community.document_loaders.pdf import PyPDFLoader
from langchain_text_splitters import CharacterTextSplitter
from langchain_postgres.vectorstores import PGVector
from langchain_community.embeddings import HuggingFaceEmbeddings
from models.embedding_service import EmbeddingProvider
from tools.embeddingTools import get_embeddings_model

from models.resource import Resource
from typing import Optional
from langchain_core.documents import Document
from typing import List

REPO_BASE_FOLDER = os.path.abspath(os.getenv("REPO_BASE_FOLDER"))
#TODO: pgVector should not know about silos
COLLECTION_PREFIX = 'silo_'

@deprecation.deprecated(
    deprecated_in="1.0.0",
    current_version="1.0.0",
    details="PGVectorTools is deprecated. Use tools.vector_store.VectorStore instead, "
            "which provides abstraction over multiple vector database backends."
)
class PGVectorTools:
    """
    DEPRECATED: Use tools.vector_store.VectorStore instead.
    
    This class is maintained for backward compatibility only.
    It internally delegates to VectorStore, which provides
    abstraction over multiple vector database backends.
    
    Migration guide:
        Old: from tools.pgVectorTools import PGVectorTools
             pg_vector_tools = PGVectorTools(db)
        
        New: from tools.vector_store import VectorStore
             vector_store = VectorStore(db)
    """
    
    def __init__(self, db):
        """
        DEPRECATED: Initialize PGVectorTools with a SQLAlchemy engine.
        
        Use VectorStore instead:
            from tools.vector_store import VectorStore
            vector_store = VectorStore(db)
        """
        warnings.warn(
            "PGVectorTools is deprecated. Use tools.vector_store.VectorStore instead.",
            DeprecationWarning,
            stacklevel=2
        )
        
        # Delegate to VectorStore
        from tools.vector_store import VectorStore
        self._vector_store = VectorStore(db)
        
        # Keep these for backward compatibility
        self.Session = db.session
        self.db = db
        self._async_engine = getattr(db, '_async_engine', None)    

    @deprecation.deprecated(
        deprecated_in="0.1.0",
        current_version="1.0.0",
        details="This method is deprecated and will be removed in a future version. Use the 'index_documents' method instead."
    )
    def index_resource(self, resource):
        """
        DEPRECATED: Indexes a resource by loading its content, splitting it into chunks, and adding it to the vector store.
        Use index_documents() method instead.
        """
        
        loader = PyPDFLoader(os.path.join(REPO_BASE_FOLDER, str(resource.repository_id), resource.uri), extract_images=False)
        pages = loader.load()
        text_splitter = CharacterTextSplitter(chunk_size=10, chunk_overlap=0)
        docs = text_splitter.split_documents(pages)

        for doc in docs:
            doc.metadata["repository_id"] = resource.repository_id
            doc.metadata["resource_id"] = resource.resource_id
            doc.metadata["silo_id"] = resource.repository.silo_id

        collection_name = COLLECTION_PREFIX + str(resource.repository.silo_id)
        self._vector_store.index_documents(collection_name, docs, resource.embedding_service)

    def index_documents(self, collection_name: str, documents: list[Document], embedding_service=None):
        """
        Indexes a list of documents in the vector collection.
        Delegates to VectorStore implementation.
        """
        return self._vector_store.index_documents(collection_name, documents, embedding_service)

    @deprecation.deprecated(
        deprecated_in="0.1.0",
        current_version="1.0.0",
        details="This method is deprecated and will be removed in a future version. Use the 'delete_documents' method instead."
    )
    def delete_resource(self, resource):
        """
        DEPRECATED: Deletes a resource from the vector store.
        Use delete_documents() method instead.
        """
        collection_name = COLLECTION_PREFIX + str(resource.repository.silo_id)
        self._vector_store.delete_documents(
            collection_name, 
            {"resource_id": {"$eq": resource.resource_id}},
            resource.embedding_service
        )

    def delete_documents(self, collection_name: str, ids, embedding_service=None):
        """
        Deletes documents from the vector collection.
        Delegates to VectorStore implementation.
        """
        return self._vector_store.delete_documents(collection_name, ids, embedding_service)

    def delete_collection(self, collection_name: str, embedding_service):
        """
        Deletes a collection from the vector database.
        Delegates to VectorStore implementation.
        """
        return self._vector_store.delete_collection(collection_name, embedding_service)
        
    
    def search_similar_documents(self, collection_name: str, query: str, embedding_service=None, filter_metadata: Optional[dict] = None, RESULTS=5):
        """
        Searches for similar documents using the configured embedding service.
        Delegates to VectorStore implementation.
        """
        return self._vector_store.search_similar_documents(
            collection_name, 
            query, 
            embedding_service, 
            filter_metadata, 
            RESULTS
        )
    
    def get_pgvector_retriever(self, collection_name: str, embedding_service=None, search_params=None, use_async=False, **kwargs):
        """
        Returns a retriever object for the vector collection.
        Delegates to VectorStore implementation.
        
        Args:
            collection_name: Name of the collection
            embedding_service: Embedding service to use
            search_params: Optional search parameters
            use_async: If True, uses async engine for async operations (e.g., in LangGraph with ainvoke)
            **kwargs: Additional arguments to pass to as_retriever
        """
        return self._vector_store.get_retriever(
            collection_name,
            embedding_service,
            search_params,
            use_async,
            **kwargs
        )


