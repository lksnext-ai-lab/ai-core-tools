"""
Unified VectorStore facade that replaces PGVectorTools.

This module provides a unified interface for vector database operations,
abstracting away the underlying implementation (PGVector, Qdrant, etc.).
It serves as a drop-in replacement for the deprecated PGVectorTools class.

Includes factory logic for creating vector store instances based on configuration.
"""

import config
from typing import List, Optional, Dict

from tools.vector_stores.vector_store_interface import VectorStoreInterface
from utils.logger import get_logger

logger = get_logger(__name__)


class VectorStoreFactory:

    # Supported vector database types (including future planned support)
    SUPPORTED_TYPES = {
        'PGVECTOR': 'PGVector (PostgreSQL with pgvector extension)',
        'QDRANT': 'Qdrant vector database',
        'PINECONE': 'Pinecone vector database (future support)',
        'WEAVIATE': 'Weaviate vector database (future support)',
        'CHROMA': 'Chroma vector database (future support)',
    }

    # Types that are currently implemented and can be selected by users
    IMPLEMENTED_TYPES = ('PGVECTOR', 'QDRANT')

    _instances: Dict[str, VectorStoreInterface] = {}

    @staticmethod
    def get_vector_store(db, vector_db_type: Optional[str] = None) -> VectorStoreInterface:
        """Return a cached vector store instance for the requested backend."""

        resolved_type = (vector_db_type or config.VECTOR_DB_TYPE or 'PGVECTOR').upper()

        if resolved_type not in VectorStoreFactory.SUPPORTED_TYPES:
            supported = ', '.join(VectorStoreFactory.SUPPORTED_TYPES.keys())
            raise ValueError(
                f"Unsupported VECTOR_DB_TYPE: {resolved_type}. Supported types: {supported}"
            )

        if resolved_type not in VectorStoreFactory.IMPLEMENTED_TYPES:
            raise NotImplementedError(
                f"{resolved_type} support is planned but not yet implemented. Currently available: "
                f"{', '.join(VectorStoreFactory.IMPLEMENTED_TYPES)}"
            )

        if resolved_type in VectorStoreFactory._instances:
            return VectorStoreFactory._instances[resolved_type]

        logger.info("Initializing vector store backend: %s", resolved_type)

        if resolved_type == 'PGVECTOR':
            instance = VectorStoreFactory._create_pgvector_backend(db)
        elif resolved_type == 'QDRANT':
            instance = VectorStoreFactory._create_qdrant_backend(db)
        else:
            # Guard clause for future implementations
            raise NotImplementedError(f"Vector DB type {resolved_type} is not implemented yet")

        VectorStoreFactory._instances[resolved_type] = instance
        return instance

    @staticmethod
    def get_available_type_options() -> List[Dict[str, str]]:
        """Expose implemented vector DB choices with human-friendly labels."""

        options: List[Dict[str, str]] = []
        for key in VectorStoreFactory.IMPLEMENTED_TYPES:
            label = VectorStoreFactory.SUPPORTED_TYPES.get(key, key)
            options.append({
                'code': key,
                'label': label
            })
        return options
        
    
    @staticmethod
    def _create_pgvector_backend(db) -> VectorStoreInterface:
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
    def _create_qdrant_backend(db) -> VectorStoreInterface:
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