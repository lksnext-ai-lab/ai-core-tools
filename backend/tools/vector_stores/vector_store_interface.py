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
        k: int = 5,
        search_type: str = "similarity",
        score_threshold: Optional[float] = None,
        fetch_k: Optional[int] = None,
        lambda_mult: Optional[float] = None,
    ) -> List[Document]:
        """
        Search for similar documents in the vector store.

        Args:
            collection_name: Name of the collection/index to search
            query: Query string or embedding vector
            embedding_service: Service to generate query embeddings
            filter_metadata: Optional metadata filters
            k: Number of results to return (default: 5)
            search_type: Search strategy — "similarity" (default),
                "similarity_score_threshold", or "mmr".
            score_threshold: Minimum relevance score; used when
                search_type="similarity_score_threshold".
            fetch_k: Candidate pool size before MMR re-ranking; used when
                search_type="mmr" (default: k*4).
            lambda_mult: MMR diversity factor 0..1; used when search_type="mmr"
                (default: 0.5).

        Returns:
            List of Document objects with similarity scores in metadata
            (_score=None for MMR results).

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
        search_type: str = "similarity",
        **kwargs
    ) -> VectorStoreRetriever:
        """
        Get a LangChain retriever for the vector store.

        Args:
            collection_name: Name of the collection/index
            embedding_service: Service to generate embeddings
            search_params: Optional search parameters (filters, k, etc.)
            use_async: Whether to use async operations
            search_type: LangChain retriever search strategy — "similarity"
                (default), "similarity_score_threshold", or "mmr".
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
    def count_documents(
        self,
        collection_name: str,
        filter_metadata: Optional[Dict[str, Any]] = None,
        min_content_length: Optional[int] = None,
        max_content_length: Optional[int] = None,
    ) -> int:
        """
        Count documents stored in a collection/index, optionally filtered.

        Args:
            collection_name: Name of the collection/index
            filter_metadata: Optional PGVector-style metadata filter
                (e.g. ``{"field": {"$eq": "value"}}``)
            min_content_length: Optional minimum length of ``page_content``
            max_content_length: Optional maximum length of ``page_content``

        Returns:
            Number of documents matching the criteria
        """
        pass

    @abstractmethod
    def update_documents_metadata(
        self,
        collection_name: str,
        filter_metadata: Dict[str, Any],
        metadata_updates: Dict[str, Any],
        replace: bool = False,
    ) -> int:
        """
        Update metadata for documents matching a metadata filter.

        Args:
            collection_name: Name of the collection/index
            filter_metadata: PGVector-style metadata filter selecting the
                documents to update.
            metadata_updates: Metadata fields to apply.
            replace: If True, the matched documents' metadata is fully replaced
                by ``metadata_updates``. If False (default), ``metadata_updates``
                is merged into the existing metadata.

        Returns:
            Number of documents updated.
        """
        pass

    @abstractmethod
    def get_distinct_metadata_values(
        self,
        collection_name: str,
        field: str,
        prefix: Optional[str] = None,
        limit: int = 100,
    ) -> List[str]:
        """
        Return distinct string values for a metadata field in a collection.

        Args:
            collection_name: Name of the collection/index
            field: Metadata field name
            prefix: Optional case-insensitive prefix filter
            limit: Maximum number of values to return

        Returns:
            Alphabetically sorted list of distinct values.
        """
        pass
