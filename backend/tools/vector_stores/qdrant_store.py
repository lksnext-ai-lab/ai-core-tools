"""
Qdrant implementation of the vector store interface.

This module provides a Qdrant-specific implementation of VectorStoreBase,
using LangChain's Qdrant integration.

Note: Requires qdrant-client package to be installed:
    pip install qdrant-client
"""

import logging
from typing import List, Optional, Dict, Any
from langchain_core.documents import Document
from langchain_core.vectorstores.base import VectorStoreRetriever

from tools.vector_stores.vector_store_interface import VectorStoreInterface
from tools.embeddingTools import get_embeddings_model

logger = logging.getLogger(__name__)


class QdrantStore(VectorStoreInterface):
    """
    Qdrant implementation of the vector store interface.
    
    This class uses Qdrant as the vector database backend. It can connect
    to Qdrant Cloud or a self-hosted Qdrant instance.
    
    Attributes:
        db: Database object (kept for API consistency, may not be used)
        url: Qdrant server URL
        api_key: Optional API key for Qdrant Cloud
        prefer_grpc: Whether to use gRPC protocol (faster)
        client: Qdrant client instance
    """
    
    def __init__(self, db, url: str, api_key: Optional[str] = None, prefer_grpc: bool = False):
        """
        Initialize Qdrant store with connection details.
        
        Args:
            db: Database object (kept for API consistency with PGVectorStore)
            url: Qdrant server URL (e.g., 'http://localhost:6333' or Qdrant Cloud URL)
            api_key: Optional API key for authentication (required for Qdrant Cloud)
            prefer_grpc: Whether to use gRPC protocol instead of REST
            
        Raises:
            ImportError: If qdrant-client package is not installed
            
        Note:
            Unlike PGVectorStore, Qdrant is a separate service and doesn't use
            the PostgreSQL connection. The db parameter is accepted for API
            consistency but may not be actively used.
        """
        try:
            from qdrant_client import QdrantClient
            from langchain_qdrant import QdrantVectorStore
        except ImportError:
            raise ImportError(
                "qdrant-client package is required for Qdrant support. "
                "Install it with: pip install qdrant-client langchain-qdrant"
            )
        
        self.db = db  # Store for potential future use (metadata queries, etc.)
        self.url = url
        self.api_key = api_key
        self.prefer_grpc = prefer_grpc
        
        # Initialize Qdrant client
        self.client = QdrantClient(
            url=url,
            api_key=api_key,
            prefer_grpc=prefer_grpc
        )
        
        self._QdrantVectorStore = QdrantVectorStore
    
    def _get_vector_store(
        self, 
        collection_name: str, 
        embedding_service=None
    ):
        """
        Internal method to create a QdrantVectorStore instance.
        
        Args:
            collection_name: Name of the collection
            embedding_service: Embedding service to use
            
        Returns:
            Configured QdrantVectorStore instance
        """
        embeddings = get_embeddings_model(embedding_service)
        
        return self._QdrantVectorStore(
            client=self.client,
            collection_name=collection_name,
            embedding=embeddings
        )
    
    def _convert_to_qdrant_filter(self, filter_metadata: Optional[Dict[str, Any]]):
        """
        Convert MongoDB-style filter to Qdrant Filter (Dict format).
        Replicates logic from frontend SearchFilters.tsx buildQdrantFilter.
        """
        if not filter_metadata:
            return None
        
        print("Converting filter metadata:", filter_metadata)
            
        # If it looks like a Qdrant filter already, return as is
        if any(key in filter_metadata for key in ['must', 'should', 'must_not', 'filter']):
            return filter_metadata

        must_conditions = []
        should_conditions = []
        must_not_conditions = []

        def _get_key(key):
            return key if key.startswith("metadata.") else f"metadata.{key}"

        def _process_condition(key, val, target_list):
            q_key = _get_key(key)
            
            if isinstance(val, dict):
                for op, op_val in val.items():
                    if op == "$eq":
                        target_list.append({"key": q_key, "match": {"value": op_val}})
                    elif op == "$ne":
                        must_not_conditions.append({"key": q_key, "match": {"value": op_val}})
                    elif op in ["$gt", "$gte", "$lt", "$lte"]:
                         # Strip $ from operator name for range dict: $gt -> gt
                        target_list.append({"key": q_key, "range": {op[1:]: op_val}})
                    elif op == "$in":
                        target_list.append({"key": q_key, "match": {"any": op_val}})
                    elif op == "$nin":
                        must_not_conditions.append({"key": q_key, "match": {"any": op_val}})
            else:
                # Direct value implies equality
                target_list.append({"key": q_key, "match": {"value": val}})

        # Handle explicit top-level operators
        if "$or" in filter_metadata and isinstance(filter_metadata["$or"], list):
            for condition in filter_metadata["$or"]:
                if isinstance(condition, dict):
                    for k, v in condition.items():
                        _process_condition(k, v, should_conditions)
        
        if "$and" in filter_metadata and isinstance(filter_metadata["$and"], list):
            for condition in filter_metadata["$and"]:
                if isinstance(condition, dict):
                    for k, v in condition.items():
                        _process_condition(k, v, must_conditions)

        # Handle flat metadata fields (implicit AND)
        for k, v in filter_metadata.items():
            if k not in ["$or", "$and"]:
                _process_condition(k, v, must_conditions)

        # Construct result dictionary - avoid empty lists
        qdrant_filter = {}
        if must_conditions:
            qdrant_filter["must"] = must_conditions
        if should_conditions:
            qdrant_filter["should"] = should_conditions
        if must_not_conditions:
            qdrant_filter["must_not"] = must_not_conditions
            
        return qdrant_filter if qdrant_filter else None
    
    def index_documents(
        self, 
        collection_name: str, 
        documents: List[Document], 
        embedding_service=None
    ) -> None:
        """
        Index documents into Qdrant collection.
        
        Creates the collection if it doesn't exist.
        
        Args:
            collection_name: Name of the collection to store documents
            documents: List of LangChain Document objects to index
            embedding_service: Service to generate embeddings
        """
        if not documents:
            return
        
        logger.info(f"Indexing {len(documents)} documents to collection {collection_name}")
        
        embeddings = get_embeddings_model(embedding_service)
        
        # Check if collection exists, create if it doesn't
        collection_exists = False
        try:
            self.client.get_collection(collection_name)
            collection_exists = True
            logger.info(f"Collection {collection_name} already exists")
        except Exception:
            logger.info(f"Collection {collection_name} doesn't exist, will create it")
        
        if not collection_exists:
            # Get embedding dimension from the embedding model
            test_embedding = embeddings.embed_query("test")
            vector_size = len(test_embedding)
            
            from qdrant_client.models import Distance, VectorParams
            
            self.client.create_collection(
                collection_name=collection_name,
                vectors_config=VectorParams(
                    size=vector_size,
                    distance=Distance.COSINE
                )
            )
            logger.info(f"Created collection {collection_name} with vector size {vector_size}")
        
        # Always use the same method to get vector store
        vector_store = self._get_vector_store(collection_name, embedding_service)
        
        # Add documents - this will generate embeddings automatically
        ids = vector_store.add_documents(documents)
        logger.info(f"Successfully added {len(ids)} documents with embeddings to collection {collection_name}")
    
    def delete_documents(
        self, 
        collection_name: str, 
        ids, 
        embedding_service=None
    ) -> None:
        """
        Delete documents from Qdrant collection.
        
        Args:
            collection_name: Name of the collection
            ids: Document IDs to delete (list) or metadata filter (dict)
            embedding_service: Service used for embeddings
            
        Note: 
            If ids is a dict (metadata filter), we first search for matching
            documents and then delete them by their IDs.
        """
        vector_store = self._get_vector_store(collection_name, embedding_service)
        
        if isinstance(ids, list):
            # Direct deletion by IDs
            vector_store.delete(ids=ids)
        else:
            # Deletion by metadata filter
            if ids is None:
                logger.warning("No valid metadata filter provided for Qdrant deletion; skipping")
                return
            
            # Translate metadata filter if needed
            qdrant_filter = self._convert_to_qdrant_filter(ids)

            # Search and get IDs
            results = self.client.scroll(
                collection_name=collection_name,
                scroll_filter=qdrant_filter,
                limit=1000,
                with_payload=False,
                with_vectors=False
            )[0]
            
            ids_to_delete = [point.id for point in results]
            
            if ids_to_delete:
                self.client.delete(
                    collection_name=collection_name,
                    points_selector=ids_to_delete
                )
    
    def delete_collection(
        self, 
        collection_name: str, 
        embedding_service=None
    ) -> None:
        """
        Delete an entire collection from Qdrant.
        
        Args:
            collection_name: Name of the collection to delete
            embedding_service: Service used for embeddings (not used in Qdrant)
        """
        self.client.delete_collection(collection_name=collection_name)
    
    def search_similar_documents(
        self,
        collection_name: str,
        query: str,
        embedding_service=None,
        filter_metadata: Optional[Dict[str, Any]] = None,
        k: int = 5
    ) -> List[Document]:
        """
        Search for similar documents in Qdrant collection.
        
        Args:
            collection_name: Name of the collection to search
            query: Query string or embedding vector
            embedding_service: Service to generate query embeddings
            filter_metadata: Optional metadata filters
            k: Number of results to return
            
        Returns:
            List of Document objects with similarity scores in metadata
        """
        vector_store = self._get_vector_store(collection_name, embedding_service)
        # Handle empty queries
        if not query or (isinstance(query, str) and not query.strip()):
            query = " "  # Use a space as minimal query
        
        # Translate metadata filter if needed
        qdrant_filter_dict = self._convert_to_qdrant_filter(filter_metadata)
        
        # Convert dict to Qdrant Filter model if not None
        qdrant_filter = None
        if qdrant_filter_dict:
            try:
                from qdrant_client import models as rest
                qdrant_filter = rest.Filter.model_validate(qdrant_filter_dict)
            except ImportError:
                # Fallback to passing the dict if models can't be imported
                qdrant_filter = qdrant_filter_dict
        
        # Perform similarity search with scores
        results_with_scores = vector_store.similarity_search_with_score(
            query,
            k=k,
            filter=qdrant_filter
        )
        
        # Convert results to include score in metadata
        results = []
        for doc, score in results_with_scores:
            new_doc = Document(
                page_content=doc.page_content,
                metadata={**doc.metadata, '_score': score}
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
        Get a LangChain retriever for Qdrant collection.
        
        Args:
            collection_name: Name of the collection
            embedding_service: Service to generate embeddings
            search_params: Optional search parameters (filters, k, etc.)
            use_async: Whether to use async operations (note: may not be fully supported)
            **kwargs: Additional arguments for retriever configuration
            
        Returns:
            VectorStoreRetriever instance configured for this collection
        """
        vector_store = self._get_vector_store(collection_name, embedding_service)
        
        if search_params is not None:
            return vector_store.as_retriever(search_kwargs=search_params, **kwargs)
        return vector_store.as_retriever(**kwargs)

    def collection_exists(self, collection_name: str) -> bool:
        try:
            self.client.get_collection(collection_name)
            return True
        except Exception as exc:
            logger.debug(f"Qdrant collection %s not found: %s", collection_name, exc)
            return False

    def count_documents(self, collection_name: str) -> int:
        try:
            response = self.client.count(collection_name)
            return int(response.count)
        except Exception as exc:
            logger.debug(f"Failed to count documents for collection %s: %s", collection_name, exc)
            return 0
