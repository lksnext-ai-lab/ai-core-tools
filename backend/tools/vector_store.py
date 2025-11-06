"""
Unified VectorStore facade that replaces PGVectorTools.

This module provides a unified interface for vector database operations,
abstracting away the underlying implementation (PGVector, Qdrant, etc.).
It serves as a drop-in replacement for the deprecated PGVectorTools class.
"""

from typing import List, Optional, Dict, Any
from langchain_core.documents import Document
from langchain_core.vectorstores.base import VectorStoreRetriever

from tools.vector_store_factory import get_vector_store
from tools.vector_store_base import VectorStoreBase


class VectorStore:
    """
    Unified vector store facade.
    
    This class provides a simple interface for vector database operations,
    delegating to the appropriate backend (PGVector, Qdrant, etc.) based
    on configuration. It's designed as a drop-in replacement for PGVectorTools.
    
    Usage:
        >>> from tools.vector_store import VectorStore
        >>> from db.database import db
        >>> 
        >>> vector_store = VectorStore(db)
        >>> vector_store.index_documents('my_collection', documents, embedding_service)
        >>> results = vector_store.search_similar_documents('my_collection', 'query')
    
    Attributes:
        _backend: The underlying VectorStoreBase implementation
    """
    
    def __init__(self, db):
        """
        Initialize VectorStore with database connection.
        
        The actual vector database backend is determined by the VECTOR_DB_TYPE
        environment variable and instantiated via the factory.
        
        Args:
            db: Database object with engine and optional _async_engine
        """
        self.db = db
        self._backend: VectorStoreBase = get_vector_store(db)
    
    def index_documents(
        self, 
        collection_name: str, 
        documents: List[Document], 
        embedding_service=None
    ) -> None:
        """
        Index a list of documents into the vector store.
        
        Args:
            collection_name: Name of the collection/index to store documents
            documents: List of LangChain Document objects to index
            embedding_service: Service to generate embeddings (optional)
            
        Example:
            >>> docs = [Document(page_content="Hello", metadata={"source": "test"})]
            >>> vector_store.index_documents('test_collection', docs, embedding_service)
        """
        return self._backend.index_documents(collection_name, documents, embedding_service)
    
    def delete_documents(
        self, 
        collection_name: str, 
        ids, 
        embedding_service=None
    ) -> None:
        """
        Delete documents from the vector store.
        
        Args:
            collection_name: Name of the collection/index
            ids: Document IDs to delete (list) or metadata filter (dict)
            embedding_service: Service used for embeddings
            
        Example:
            >>> # Delete by IDs
            >>> vector_store.delete_documents('test_collection', ['id1', 'id2'])
            >>> 
            >>> # Delete by filter
            >>> vector_store.delete_documents('test_collection', {"source": "test"})
        """
        return self._backend.delete_documents(collection_name, ids, embedding_service)
    
    def delete_collection(
        self, 
        collection_name: str, 
        embedding_service=None
    ) -> None:
        """
        Delete an entire collection/index from the vector store.
        
        Args:
            collection_name: Name of the collection/index to delete
            embedding_service: Service used for embeddings
            
        Example:
            >>> vector_store.delete_collection('test_collection', embedding_service)
        """
        return self._backend.delete_collection(collection_name, embedding_service)
    
    def search_similar_documents(
        self,
        collection_name: str,
        query: str,
        embedding_service=None,
        filter_metadata: Optional[Dict[str, Any]] = None,
        RESULTS: int = 5
    ) -> List[Document]:
        """
        Search for similar documents in the vector store.
        
        Note: Parameter name is RESULTS (not k) for backward compatibility with PGVectorTools.
        
        Args:
            collection_name: Name of the collection/index to search
            query: Query string or embedding vector
            embedding_service: Service to generate query embeddings
            filter_metadata: Optional metadata filters
            RESULTS: Number of results to return (default: 5)
            
        Returns:
            List of Document objects with similarity scores in metadata (_score, _id)
            
        Example:
            >>> results = vector_store.search_similar_documents(
            ...     'test_collection',
            ...     'What is AI?',
            ...     embedding_service,
            ...     filter_metadata={"source": "docs"},
            ...     RESULTS=10
            ... )
            >>> for doc in results:
            ...     print(f"Score: {doc.metadata['_score']}, Content: {doc.page_content}")
        """
        return self._backend.search_similar_documents(
            collection_name, 
            query, 
            embedding_service, 
            filter_metadata, 
            k=RESULTS
        )
    
    def get_retriever(
        self,
        collection_name: str,
        embedding_service=None,
        search_params: Optional[Dict[str, Any]] = None,
        use_async: bool = False,
        **kwargs
    ) -> VectorStoreRetriever:
        """
        Get a LangChain retriever for the vector store.
        
        This method is compatible with the deprecated get_pgvector_retriever method.
        
        Args:
            collection_name: Name of the collection/index
            embedding_service: Service to generate embeddings
            search_params: Optional search parameters (filters, k, etc.)
            use_async: Whether to use async operations (for LangGraph, etc.)
            **kwargs: Additional arguments for retriever configuration
            
        Returns:
            VectorStoreRetriever instance
            
        Example:
            >>> retriever = vector_store.get_retriever(
            ...     'test_collection',
            ...     embedding_service,
            ...     search_params={'k': 5, 'filter': {'source': 'docs'}},
            ...     use_async=True
            ... )
            >>> results = retriever.invoke("What is AI?")
        """
        return self._backend.get_retriever(
            collection_name,
            embedding_service,
            search_params,
            use_async,
            **kwargs
        )
    
    # Alias for backward compatibility with PGVectorTools
    def get_pgvector_retriever(
        self,
        collection_name: str,
        embedding_service=None,
        search_params: Optional[Dict[str, Any]] = None,
        use_async: bool = False,
        **kwargs
    ) -> VectorStoreRetriever:
        """
        Deprecated: Use get_retriever() instead.
        
        This method is provided for backward compatibility with code
        that still uses the old PGVectorTools interface.
        """
        return self.get_retriever(
            collection_name,
            embedding_service,
            search_params,
            use_async,
            **kwargs
        )

    def collection_exists(self, collection_name: str) -> bool:
        """Check if a collection exists in the configured vector store."""
        return self._backend.collection_exists(collection_name)

    def count_documents(self, collection_name: str) -> int:
        """Return the number of documents stored in a collection."""
        return self._backend.count_documents(collection_name)
