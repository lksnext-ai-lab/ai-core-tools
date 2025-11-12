"""
Abstract base class for vector database operations.

This module defines the interface that all vector store implementations must follow.
It provides abstraction over different vector database backends (PGVector, Qdrant, etc.)
while maintaining a consistent API for the rest of the application.
"""

from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any
from langchain_core.documents import Document
from langchain_core.vectorstores.base import VectorStoreRetriever


class VectorStoreInterface(ABC):
    """
    Abstract base class for vector database operations.
    
    All vector store implementations (PGVector, Qdrant, etc.) must implement this interface.
    This allows the application to switch between different vector databases without
    changing the business logic.
    """
    
    @abstractmethod
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
            embedding_service: Service to generate embeddings (optional, uses default if None)
            
        Raises:
            Exception: If indexing fails
        """
        pass
    
    @abstractmethod
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
            ids: Document IDs to delete (can be list or dict filter)
            embedding_service: Service used for embeddings (may be needed for some operations)
            
        Raises:
            Exception: If deletion fails
        """
        pass
    
    @abstractmethod
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
            
        Raises:
            Exception: If deletion fails
        """
        pass
    
    @abstractmethod
    def search_similar_documents(
        self,
        collection_name: str,
        query: str,
        embedding_service=None,
        filter_metadata: Optional[Dict[str, Any]] = None,
        k: int = 5
    ) -> List[Document]:
        """
        Search for similar documents in the vector store.
        
        Args:
            collection_name: Name of the collection/index to search
            query: Query string or embedding vector
            embedding_service: Service to generate query embeddings
            filter_metadata: Optional metadata filters
            k: Number of results to return (default: 5)
            
        Returns:
            List of Document objects with similarity scores in metadata
            
        Raises:
            Exception: If search fails
        """
        pass
    
    @abstractmethod
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
        
        Args:
            collection_name: Name of the collection/index
            embedding_service: Service to generate embeddings
            search_params: Optional search parameters (filters, k, etc.)
            use_async: Whether to use async operations
            **kwargs: Additional arguments for retriever configuration
            
        Returns:
            VectorStoreRetriever instance
            
        Raises:
            Exception: If retriever creation fails
        """
        pass

    @abstractmethod
    def collection_exists(self, collection_name: str) -> bool:
        """
        Check if a collection/index exists in the vector store.

        Args:
            collection_name: Name of the collection/index to check

        Returns:
            True if the collection exists, False otherwise
        """
        pass

    @abstractmethod
    def count_documents(self, collection_name: str) -> int:
        """
        Count the number of documents stored in a collection/index.

        Args:
            collection_name: Name of the collection/index

        Returns:
            Number of documents stored in the collection
        """
        pass
