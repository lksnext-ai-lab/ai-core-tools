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
            prefer_grpc=prefer_grpc,
            timeout=60,
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
    
    # Top-level keys that identify an already-formatted Qdrant native filter
    _QDRANT_NATIVE_KEYS: frozenset = frozenset({'must', 'should', 'must_not', 'min_should'})

    _PGVECTOR_TO_QDRANT_OPERATOR: Dict[str, str] = {
        '$eq': 'match',
        '$ne': 'must_not_match',
        '$gt': 'gt',
        '$gte': 'gte',
        '$lt': 'lt',
        '$lte': 'lte',
    }

    _QDRANT_METADATA_PREFIX = 'metadata.'

    def _is_qdrant_native_filter(self, filter_dict: Dict[str, Any]) -> bool:
        """
        Return True if filter_dict is already in Qdrant native format.

        Qdrant native filters use only the clause keys: must, should, must_not, min_should.
        PGVector-style filters use field names as keys with operator dicts as values.
        """
        return bool(filter_dict) and all(key in self._QDRANT_NATIVE_KEYS for key in filter_dict)

    def _translate_pgvector_filter_to_qdrant(self, filter_dict: Dict[str, Any]) -> Dict[str, Any]:
        """
        Translate a PGVector-style filter dict to Qdrant native filter format.

        PGVector format:  {"field": {"$op": value}, ...}
        Qdrant format:    {"must": [...], "must_not": [...]}

        Supported operators: $eq, $ne, $gt, $gte, $lt, $lte, $in
        """
        must: List[Dict[str, Any]] = []
        must_not: List[Dict[str, Any]] = []

        for field_name, condition in filter_dict.items():
            if not isinstance(condition, dict):
                # Plain equality shorthand: {"field": value}
                must.append({
                    'key': f'{self._QDRANT_METADATA_PREFIX}{field_name}',
                    'match': {'value': condition},
                })
                continue

            for operator, value in condition.items():
                key = f'{self._QDRANT_METADATA_PREFIX}{field_name}'

                if operator == '$in':
                    if not isinstance(value, list) or not value:
                        logger.warning(
                            "Qdrant filter: $in value for field '%s' is empty or not a list; condition discarded",
                            field_name,
                        )
                        continue
                    must.append({'key': key, 'match': {'any': value}})
                    continue

                native_op = self._PGVECTOR_TO_QDRANT_OPERATOR.get(operator)
                if native_op is None:
                    logger.warning(f"Unknown filter operator '{operator}' for Qdrant; skipping field '{field_name}'")
                    continue

                if native_op == 'must_not_match':
                    must_not.append({'key': key, 'match': {'value': value}})
                elif native_op == 'match':
                    must.append({'key': key, 'match': {'value': value}})
                else:
                    must.append({'key': key, 'range': {native_op: value}})

        qdrant_filter: Dict[str, Any] = {}
        if must:
            qdrant_filter['must'] = must
        if must_not:
            qdrant_filter['must_not'] = must_not

        return qdrant_filter

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
            embedding_service: Service used for embeddings (only required for
                list-based deletion via the LangChain vector-store wrapper;
                filter-based deletion uses the raw client and does not need it).

        Note:
            When ``ids`` is a dict (metadata filter), Qdrant's native
            filter-based delete is used — no embedding service is required and
            all matching points are removed regardless of collection size.
        """
        if isinstance(ids, list):
            vector_store = self._get_vector_store(collection_name, embedding_service)
            vector_store.delete(ids=ids)
        else:
            # Native filter-based delete removes all matching points atomically
            # regardless of collection size (no scroll/page-size limit).
            if ids is None:
                logger.warning("No valid metadata filter provided for Qdrant deletion; skipping")
                return

            qdrant_filter = self._build_qdrant_filter(ids)
            if qdrant_filter is None:
                logger.warning(
                    "Qdrant delete_documents: filter translated to None for collection %s; skipping",
                    collection_name,
                )
                return

            from qdrant_client.models import FilterSelector

            self.client.delete(
                collection_name=collection_name,
                points_selector=FilterSelector(filter=qdrant_filter),
            )
            logger.debug(
                "Qdrant delete_documents: issued filter-based delete on collection %s",
                collection_name,
            )
    
    def delete_documents_excluding(
        self,
        collection_name: str,
        filter_metadata: Dict[str, Any],
        exclude: Dict[str, Any],
        embedding_service=None,
    ) -> None:
        if not filter_metadata:
            raise ValueError("filter_metadata is required for delete_documents_excluding")

        from qdrant_client.models import Filter, FieldCondition, MatchValue, FilterSelector

        base = self._build_qdrant_filter(filter_metadata)
        if base is None:
            logger.warning(
                "Qdrant delete_documents_excluding: filter translated to None for %s; skipping",
                collection_name,
            )
            return

        # must_not on the fresh-batch marker preserves the just-written chunks; points
        # lacking the field do not match must_not and are deleted (legacy chunks included).
        must_not = [FieldCondition(key=f, match=MatchValue(value=v)) for f, v in exclude.items()]
        combined = Filter(
            must=list(base.must or []),
            should=list(base.should or []),
            must_not=list(base.must_not or []) + must_not,
        )
        self.client.delete(
            collection_name=collection_name,
            points_selector=FilterSelector(filter=combined),
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
        k: int = 5,
        search_type: str = "similarity",
        score_threshold: Optional[float] = None,
        fetch_k: Optional[int] = None,
        lambda_mult: Optional[float] = None,
    ) -> List[Document]:
        """
        Search for similar documents in Qdrant collection.

        Args:
            collection_name: Name of the collection to search
            query: Query string or embedding vector
            embedding_service: Service to generate query embeddings
            filter_metadata: Optional metadata filters
            k: Number of results to return
            search_type: Search strategy — "similarity" (default),
                "similarity_score_threshold", or "mmr".
            score_threshold: Minimum relevance score for
                "similarity_score_threshold" search.
            fetch_k: Candidate pool size before MMR re-ranking (default: k*4).
            lambda_mult: MMR diversity factor 0..1 (default: 0.5).

        Returns:
            List of Document objects with similarity scores in metadata
            (_score=None for MMR results).
        """
        vector_store = self._get_vector_store(collection_name, embedding_service)

        # Translate PGVector-style filter dict to a qdrant_client.models.Filter object
        # once before dispatching.  QdrantVectorStore.filter= expects models.Filter | None
        # (not a raw dict) — passing a dict is silently mishandled or raises at runtime.
        qdrant_filter = self._build_qdrant_filter(filter_metadata) if filter_metadata else None

        if not query or (isinstance(query, str) and not query.strip()):
            query = " "

        if search_type == "mmr":
            docs = vector_store.max_marginal_relevance_search(
                query,
                k=k,
                filter=qdrant_filter,
                fetch_k=fetch_k if fetch_k else k * 4,
                lambda_mult=lambda_mult if lambda_mult is not None else 0.5,
            )
            return [
                Document(
                    page_content=doc.page_content,
                    metadata={**doc.metadata, '_score': None},
                )
                for doc in docs
            ]

        if search_type == "similarity_score_threshold" and score_threshold is not None:
            results_with_scores = vector_store.similarity_search_with_relevance_scores(
                query,
                k=k,
                filter=qdrant_filter,
                score_threshold=score_threshold,
            )
            return [
                Document(
                    page_content=doc.page_content,
                    metadata={**doc.metadata, '_score': score},
                )
                for doc, score in results_with_scores
            ]

        # Default: similarity search
        results_with_scores = vector_store.similarity_search_with_score(
            query,
            k=k,
            filter=qdrant_filter
        )
        return [
            Document(
                page_content=doc.page_content,
                metadata={**doc.metadata, '_score': score},
            )
            for doc, score in results_with_scores
        ]
    
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
        Get a LangChain retriever for Qdrant collection.

        Args:
            collection_name: Name of the collection
            embedding_service: Service to generate embeddings
            search_params: Optional search parameters (filters, k, etc.)
            use_async: Whether to use async operations (note: may not be fully supported)
            search_type: LangChain retriever search strategy — "similarity"
                (default), "similarity_score_threshold", or "mmr".
            **kwargs: Additional arguments for retriever configuration

        Returns:
            VectorStoreRetriever instance configured for this collection
        """
        vector_store = self._get_vector_store(collection_name, embedding_service)

        if search_params is not None:
            # as_retriever forwards search_kwargs verbatim; the underlying search
            # expects models.Filter | None, not a raw dict.
            translated_params = dict(search_params)
            if "filter" in translated_params and isinstance(translated_params["filter"], dict):
                translated_params["filter"] = self._build_qdrant_filter(translated_params["filter"])
            return vector_store.as_retriever(
                search_type=search_type,
                search_kwargs=translated_params,
                **kwargs
            )
        return vector_store.as_retriever(search_type=search_type, **kwargs)

    def collection_exists(self, collection_name: str) -> bool:
        try:
            self.client.get_collection(collection_name)
            return True
        except Exception as exc:
            logger.debug(f"Qdrant collection %s not found: %s", collection_name, exc)
            return False

    def count_documents(
        self,
        collection_name: str,
        filter_metadata: Optional[Dict[str, Any]] = None,
        min_content_length: Optional[int] = None,
        max_content_length: Optional[int] = None,
    ) -> int:
        try:
            qdrant_filter = self._build_qdrant_filter(filter_metadata)

            # Content-length filtering must be done in-memory (no native operator).
            if min_content_length is not None or max_content_length is not None:
                return self._count_with_content_length_filter(
                    collection_name, qdrant_filter, min_content_length, max_content_length
                )

            response = self.client.count(
                collection_name=collection_name,
                count_filter=qdrant_filter,
                exact=True,
            )
            return int(response.count)
        except Exception as exc:
            logger.debug("Qdrant count_documents error for %s: %s", collection_name, exc)
            return 0

    def update_documents_metadata(
        self,
        collection_name: str,
        filter_metadata: Dict[str, Any],
        metadata_updates: Dict[str, Any],
        replace: bool = False,
    ) -> int:
        if not filter_metadata:
            raise ValueError("filter_metadata is required for update_documents_metadata")

        qdrant_filter = self._build_qdrant_filter(filter_metadata)
        if qdrant_filter is None:
            return 0

        updated = 0
        for batch in self._iter_filtered_points(collection_name, qdrant_filter):
            updated += self._apply_metadata_updates(
                collection_name, batch, metadata_updates, replace
            )
        return updated

    def _iter_filtered_points(self, collection_name: str, qdrant_filter, batch_size: int = 200):
        """Yield successive batches of points matching ``qdrant_filter``."""
        offset = None
        while True:
            results, next_offset = self.client.scroll(
                collection_name=collection_name,
                scroll_filter=qdrant_filter,
                limit=batch_size,
                offset=offset,
                with_payload=True,
                with_vectors=False,
            )
            if not results:
                return
            yield results
            if next_offset is None or len(results) < batch_size:
                return
            offset = next_offset

    def _apply_metadata_updates(
        self,
        collection_name: str,
        points,
        metadata_updates: Dict[str, Any],
        replace: bool,
    ) -> int:
        """Apply metadata updates to a batch of points; return number updated."""
        for point in points:
            if replace:
                new_metadata = dict(metadata_updates)
            else:
                payload = point.payload or {}
                existing = payload.get("metadata", {}) if isinstance(payload, dict) else {}
                new_metadata = {**existing, **metadata_updates}

            self.client.set_payload(
                collection_name=collection_name,
                payload={"metadata": new_metadata},
                points=[point.id],
            )
        return len(points)

    def get_distinct_metadata_values(
        self,
        collection_name: str,
        field: str,
        prefix: Optional[str] = None,
        limit: int = 100,
    ) -> List[str]:
        seen: set = set()
        offset = None
        batch_size = 200

        try:
            while len(seen) < limit:
                results, next_offset = self.client.scroll(
                    collection_name=collection_name,
                    limit=batch_size,
                    offset=offset,
                    with_payload=True,
                    with_vectors=False,
                )
                self._collect_metadata_values(results, field, prefix, seen)
                if next_offset is None or len(results) < batch_size:
                    break
                offset = next_offset
        except Exception as exc:
            logger.warning(
                "Qdrant get_distinct_metadata_values for %s.%s failed; partial results: %s",
                collection_name, field, exc,
            )

        return sorted(seen)[:limit]

    @staticmethod
    def _collect_metadata_values(points, field: str, prefix: Optional[str], seen: set) -> None:
        """Collect matching metadata values from a batch of points into ``seen``."""
        for point in points:
            payload = point.payload or {}
            metadata = payload.get("metadata", payload) if isinstance(payload, dict) else {}
            val = metadata.get(field) if isinstance(metadata, dict) else None
            if val is None:
                continue
            str_val = str(val)
            if prefix and not str_val.lower().startswith(prefix.lower()):
                continue
            seen.add(str_val)

    def _build_qdrant_filter(self, filter_metadata: Optional[Dict[str, Any]]):
        """
        Build a Qdrant native ``Filter`` object from a PGVector-style filter dict.
        Returns ``None`` when no filter is provided.
        """
        if not filter_metadata:
            return None

        try:
            from qdrant_client.models import Filter
        except ImportError:
            raise ImportError("qdrant-client is required for Qdrant filter building")

        if self._is_qdrant_native_filter(filter_metadata):
            native_dict = filter_metadata
        else:
            native_dict = self._translate_pgvector_filter_to_qdrant(filter_metadata)

        if not native_dict:
            return None

        return Filter(**native_dict)

    def _count_with_content_length_filter(
        self,
        collection_name: str,
        qdrant_filter,
        min_content_length: Optional[int],
        max_content_length: Optional[int],
    ) -> int:
        """In-memory content-length filtering via scroll (capped at 10k points)."""
        try:
            all_docs, _ = self.client.scroll(
                collection_name=collection_name,
                scroll_filter=qdrant_filter,
                with_payload=True,
                with_vectors=False,
                limit=10000,
            )
            if len(all_docs) == 10000:
                logger.warning(
                    "Qdrant count_documents: hit scroll cap of 10000; count may be underestimated"
                )
            count = 0
            for point in all_docs:
                content = (point.payload or {}).get("page_content", "")
                length = len(content)
                if min_content_length is not None and length < min_content_length:
                    continue
                if max_content_length is not None and length > max_content_length:
                    continue
                count += 1
            return count
        except Exception as exc:
            logger.error("Qdrant content-length count error: %s", exc)
            return 0
