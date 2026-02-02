"""
PGVector implementation of the vector store interface.

This module provides a PGVector-specific implementation of VectorStoreBase,
wrapping LangChain's PGVector functionality while conforming to our abstract interface.
"""

import numpy as np
from typing import List, Optional, Dict, Any
from sqlalchemy import text
from langchain_core.documents import Document
from langchain_core.vectorstores.base import VectorStoreRetriever
from langchain_postgres.vectorstores import PGVector

from tools.vector_stores.vector_store_interface import VectorStoreInterface
from tools.embeddingTools import get_embeddings_model


class PGVectorStore(VectorStoreInterface):
    """
    PGVector implementation of the vector store interface.
    
    This class uses PostgreSQL with the pgvector extension as the vector database.
    It wraps LangChain's PGVector class to provide a consistent interface.
    
    Attributes:
        engine: SQLAlchemy engine for database connections
        async_engine: Optional async SQLAlchemy engine for async operations
    """
    
    def __init__(self, db):
        """
        Initialize PGVector store with database connection.
        
        Args:
            db: Database object with engine and optional _async_engine attributes
        """
        self.db = db
        self.engine = db.engine
        self.async_engine = getattr(db, '_async_engine', None)
    
    def _get_vector_store(
        self, 
        collection_name: str, 
        embedding_service=None,
        use_async: bool = False
    ) -> PGVector:
        """
        Internal method to create a PGVector instance.
        
        Args:
            collection_name: Name of the collection
            embedding_service: Embedding service to use
            use_async: Whether to use async engine
            
        Returns:
            Configured PGVector instance
        """
        connection = self.async_engine if (use_async and self.async_engine) else self.engine
        
        return PGVector(
            embeddings=get_embeddings_model(embedding_service),
            collection_name=collection_name,
            connection=connection,
            use_jsonb=True,
        )
    
    def index_documents(
        self, 
        collection_name: str, 
        documents: List[Document], 
        embedding_service=None
    ) -> None:
        """
        Index documents into PGVector collection.
        
        Args:
            collection_name: Name of the collection to store documents
            documents: List of LangChain Document objects to index
            embedding_service: Service to generate embeddings
        """
        if not documents:
            return
            
        vector_store = self._get_vector_store(collection_name, embedding_service)
        vector_store.add_documents(documents)
    
    def delete_documents(
        self, 
        collection_name: str, 
        ids, 
        embedding_service=None
    ) -> None:
        """
        Delete documents from PGVector collection.
        
        Args:
            collection_name: Name of the collection
            ids: Document IDs to delete (list) or metadata filter (dict)
            embedding_service: Service used for embeddings
        """
        vector_store = self._get_vector_store(collection_name, embedding_service)
        
        if isinstance(ids, list):
            # Direct deletion by IDs
            vector_store.delete(ids=ids)
        else:
            # Deletion by metadata filter
            # TODO: For deleting docs, embedding_service should not be needed. 
            # In fact, if api key fails we cannot delete docs.
            results = vector_store.similarity_search("", k=1000, filter=ids)
            ids_array = [doc.id for doc in results]
            vector_store.delete(ids=ids_array)
    
    def delete_collection(
        self, 
        collection_name: str, 
        embedding_service=None
    ) -> None:
        """
        Delete an entire collection from PGVector.
        
        Args:
            collection_name: Name of the collection to delete
            embedding_service: Service used for embeddings
        """
        vector_store = self._get_vector_store(collection_name, embedding_service)
        vector_store.delete_collection()
    
    def search_similar_documents(
        self,
        collection_name: str,
        query: str,
        embedding_service=None,
        filter_metadata: Optional[Dict[str, Any]] = None,
        k: int = 5
    ) -> List[Document]:
        """
        Search for similar documents in PGVector collection.
        
        Args:
            collection_name: Name of the collection to search
            query: Query string or embedding vector
            embedding_service: Service to generate query embeddings
            filter_metadata: Optional metadata filters
            k: Number of results to return
            
        Returns:
            List of Document objects with similarity scores and IDs in metadata
        """
        vector_store = self._get_vector_store(collection_name, embedding_service)
        
        # Handle empty queries by returning documents with just metadata filtering
        if not query or (isinstance(query, str) and not query.strip()):
            # For empty queries, use a space as minimal query
            results_with_scores = vector_store.similarity_search_with_score(
                " ",
                k=k,
                filter=filter_metadata
            )
        elif isinstance(query, (list, np.ndarray)):
            # If we receive the embedding directly, use it
            results_with_scores = vector_store.similarity_search_with_score_by_vector(
                embedding=query,
                k=k,
                filter=filter_metadata
            )
        else:
            # Normal text search with scores
            results_with_scores = vector_store.similarity_search_with_score(
                query,
                k=k,
                filter=filter_metadata
            )
        
        # Convert the results to include score and id in metadata
        results = []
        for doc, score in results_with_scores:
            # Create a new Document with score AND id in metadata
            new_doc = Document(
                page_content=doc.page_content,
                metadata={**doc.metadata, '_score': score, '_id': doc.id}
            )
            results.append(new_doc)
            
        return results
    
    def get_retriever(
        self,
        collection_name: str,
        embedding_service=None,
        search_params: Optional[Dict[str, Any]] = None,
        use_async: bool = False,
        **kwargs
    ) -> VectorStoreRetriever:
        """
        Get a LangChain retriever for PGVector collection.
        
        Args:
            collection_name: Name of the collection
            embedding_service: Service to generate embeddings
            search_params: Optional search parameters (filters, k, etc.)
            use_async: If True, uses async engine for async operations (e.g., in LangGraph)
            **kwargs: Additional arguments to pass to as_retriever
            
        Returns:
            VectorStoreRetriever instance configured for this collection
        """
        vector_store = self._get_vector_store(collection_name, embedding_service, use_async)
        
        if search_params is not None:
            return vector_store.as_retriever(search_kwargs=search_params, **kwargs)
        return vector_store.as_retriever(**kwargs)

    def collection_exists(self, collection_name: str) -> bool:
        with self.engine.connect() as connection:
            result = connection.execute(
                text("SELECT 1 FROM langchain_pg_collection WHERE name = :name LIMIT 1"),
                {"name": collection_name}
            )
            return result.scalar() is not None

    def count_documents(self, collection_name: str) -> int:
        with self.engine.connect() as connection:
            collection_uuid = connection.execute(
                text("SELECT uuid FROM langchain_pg_collection WHERE name = :name"),
                {"name": collection_name}
            ).scalar()

            if not collection_uuid:
                return 0

            count = connection.execute(
                text("SELECT COUNT(*) FROM langchain_pg_embedding WHERE collection_id = :uuid"),
                {"uuid": collection_uuid}
            ).scalar()

            return int(count or 0)
