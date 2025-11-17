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

from tools.vector_stores.vector_store_interface import VectorStoreInterface
from utils.logger import get_logger

logger = get_logger(__name__)



class VectorStoreFactory:

    
    # Supported vector database types
    SUPPORTED_TYPES = {
        'PGVECTOR': 'PGVector (PostgreSQL with pgvector extension)',
        'QDRANT': 'Qdrant vector database',
        'PINECONE': 'Pinecone vector database (future support)',
        'WEAVIATE': 'Weaviate vector database (future support)',
        'CHROMA': 'Chroma vector database (future support)',
    }
    
    
    
    @staticmethod
    def get_vector_store(db) -> VectorStoreInterface:
        """
        Get or create the singleton backend instance.
        
        Args:
            db: Database object
            
        Returns:
            VectorStoreBase implementation instance
            
        Raises:
            ValueError: If VECTOR_DB_TYPE is not supported or required config is missing
        """
        
        vector_db_type = config.VECTOR_DB_TYPE
        
        logger.info(f"Initializing vector store backend: {vector_db_type}")
        
        # Validate that the type is supported
        if vector_db_type not in VectorStoreFactory.SUPPORTED_TYPES:
            supported = ', '.join(VectorStoreFactory.SUPPORTED_TYPES.keys())
            raise ValueError(
                f"Unsupported VECTOR_DB_TYPE: {vector_db_type}. "
                f"Supported types: {supported}"
            )   
        
        # Create the appropriate vector store instance
        if vector_db_type == 'PGVECTOR':
            return VectorStoreFactory._create_pgvector_backend(db)
            
        elif vector_db_type == 'QDRANT':
            return VectorStoreFactory._create_qdrant_backend(db)
            
        elif vector_db_type in ['PINECONE', 'WEAVIATE', 'CHROMA']:
            raise NotImplementedError(
                f"{vector_db_type} support is planned but not yet implemented. "
                f"Currently supported: PGVECTOR, QDRANT"
            )
        
    
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