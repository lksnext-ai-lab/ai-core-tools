"""
Unified VectorStore facade that replaces PGVectorTools.

This module provides a unified interface for vector database operations,
abstracting away the underlying implementation (PGVector, Qdrant, etc.).
It serves as a drop-in replacement for the deprecated PGVectorTools class.

Includes factory logic for creating vector store instances based on configuration.
"""

import config
from typing import List, Optional, Dict, Any
from langchain_core.documents import Document
from langchain_core.vectorstores.base import VectorStoreRetriever

from tools.vector_store_base import VectorStoreBase
from utils.logger import get_logger

logger = get_logger(__name__)

# Singleton instance for the backend
_backend_instance: Optional[VectorStoreBase] = None


class VectorStore:
    """
    Unified vector store facade with integrated factory logic.
    
    This class provides a simple interface for vector database operations,
    delegating to the appropriate backend (PGVector, Qdrant, etc.) based
    on configuration. It's designed as a drop-in replacement for PGVectorTools.
    
    The class automatically creates the appropriate backend implementation based
    on the VECTOR_DB_TYPE environment variable, implementing a singleton pattern
    for the backend to ensure efficiency.
    
    Usage:
        >>> from tools.vector_store import VectorStore
        >>> from db.database import db
        >>> 
        >>> vector_store = VectorStore(db)
        >>> vector_store.index_documents('my_collection', documents, embedding_service)
        >>> results = vector_store.search_similar_documents('my_collection', 'query')
    
    Attributes:
        _backend: The underlying VectorStoreBase implementation (shared across instances)
    """
    
    # Supported vector database types
    SUPPORTED_TYPES = {
        'PGVECTOR': 'PGVector (PostgreSQL with pgvector extension)',
        'QDRANT': 'Qdrant vector database',
        'PINECONE': 'Pinecone vector database (future support)',
        'WEAVIATE': 'Weaviate vector database (future support)',
        'CHROMA': 'Chroma vector database (future support)',
    }
    
    def __init__(self, db):
        """
        Initialize VectorStore with database connection.
        
        The actual vector database backend is determined by the VECTOR_DB_TYPE
        environment variable and instantiated on first use (singleton pattern).
        
        Args:
            db: Database object with engine and optional _async_engine
        """
        self.db = db
        self._backend: VectorStoreBase = self._get_or_create_backend(db)
    
    @staticmethod
    def _get_or_create_backend(db) -> VectorStoreBase:
        """
        Get or create the singleton backend instance.
        
        Args:
            db: Database object
            
        Returns:
            VectorStoreBase implementation instance
            
        Raises:
            ValueError: If VECTOR_DB_TYPE is not supported or required config is missing
        """
        global _backend_instance
        
        # Return existing instance if available
        if _backend_instance is not None:
            return _backend_instance
        
        vector_db_type = config.VECTOR_DB_TYPE
        
        logger.info(f"Initializing vector store backend: {vector_db_type}")
        
        # Validate that the type is supported
        if vector_db_type not in VectorStore.SUPPORTED_TYPES:
            supported = ', '.join(VectorStore.SUPPORTED_TYPES.keys())
            raise ValueError(
                f"Unsupported VECTOR_DB_TYPE: {vector_db_type}. "
                f"Supported types: {supported}"
            )
        
        # Create the appropriate vector store instance
        if vector_db_type == 'PGVECTOR':
            _backend_instance = VectorStore._create_pgvector_backend(db)
            
        elif vector_db_type == 'QDRANT':
            _backend_instance = VectorStore._create_qdrant_backend(db)
            
        elif vector_db_type in ['PINECONE', 'WEAVIATE', 'CHROMA']:
            raise NotImplementedError(
                f"{vector_db_type} support is planned but not yet implemented. "
                f"Currently supported: PGVECTOR, QDRANT"
            )
        
        logger.info(f"Vector store backend initialized: {vector_db_type}")
        return _backend_instance
    
    @staticmethod
    def _create_pgvector_backend(db) -> VectorStoreBase:
        """
        Create PGVector backend instance.
        
        Args:
            db: Database object
            
        Returns:
            PGVectorStore instance
        """
        from tools.vector_stores.pgvector_store import PGVectorStore
        
        logger.debug("Creating PGVector store with existing database connection")
        return PGVectorStore(db)
    
    @staticmethod
    def _create_qdrant_backend(db) -> VectorStoreBase:
        """
        Create Qdrant backend instance.
        
        Args:
            db: Database object (passed for API consistency)
            
        Returns:
            QdrantStore instance
            
        Raises:
            ValueError: If required Qdrant configuration is missing
        """
        from tools.vector_stores.qdrant_store import QdrantStore
        
        if not config.QDRANT_URL:
            raise ValueError(
                "QDRANT_URL environment variable is required when VECTOR_DB_TYPE=QDRANT"
            )
        
        logger.debug(f"Creating Qdrant store with URL: {config.QDRANT_URL}")
        return QdrantStore(
            db=db,
            url=config.QDRANT_URL,
            api_key=config.QDRANT_API_KEY,
            prefer_grpc=config.QDRANT_PREFER_GRPC
        )
    
    @classmethod
    def reset_backend(cls):
        """
        Reset the singleton backend instance.
        
        This is useful for testing or when you need to reinitialize
        the vector store with different configuration.
        """
        global _backend_instance
        _backend_instance = None
        logger.info("Vector store backend instance reset")
    
    @staticmethod
    def get_current_type() -> str:
        """
        Get the currently configured vector database type.
        
        Returns:
            String indicating the vector DB type (e.g., 'PGVECTOR', 'QDRANT')
        """
        return config.VECTOR_DB_TYPE
    
    @classmethod
    def get_supported_types(cls) -> dict:
        """
        Get dictionary of supported vector database types.
        
        Returns:
            Dictionary mapping type codes to descriptions
        """
        return cls.SUPPORTED_TYPES.copy()
    
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
