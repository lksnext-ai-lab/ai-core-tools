"""
Factory for creating vector store instances based on configuration.

This module implements the Factory pattern to instantiate the appropriate
vector store implementation based on the VECTOR_DB_TYPE environment variable.
Uses singleton pattern to ensure only one instance per database type.
"""

import config
from typing import Optional
from tools.vector_store_base import VectorStoreBase
from utils.logger import get_logger

logger = get_logger(__name__)

# Singleton instance
_vector_store_instance: Optional[VectorStoreBase] = None


class VectorStoreFactory:
    """
    Factory class for creating vector store instances.
    
    This factory reads the VECTOR_DB_TYPE environment variable and returns
    the appropriate vector store implementation. Implements singleton pattern
    to ensure only one instance exists per application.
    """
    
    SUPPORTED_TYPES = {
        'PGVECTOR': 'PGVector (PostgreSQL with pgvector extension)',
        'QDRANT': 'Qdrant vector database',
        'PINECONE': 'Pinecone vector database (future support)',
        'WEAVIATE': 'Weaviate vector database (future support)',
        'CHROMA': 'Chroma vector database (future support)',
    }
    
    @staticmethod
    def create_vector_store(db) -> VectorStoreBase:
        """
        Create and return a vector store instance based on configuration.
        
        This method implements the singleton pattern - it returns the same instance
        on subsequent calls unless reset() is called.
        
        Args:
            db: Database object with engine and optional _async_engine
            
        Returns:
            VectorStoreBase implementation instance
            
        Raises:
            ValueError: If VECTOR_DB_TYPE is not supported or required config is missing
        """
        global _vector_store_instance
        
        # Return existing instance if available
        if _vector_store_instance is not None:
            return _vector_store_instance
        
        vector_db_type = config.VECTOR_DB_TYPE
        
        logger.info(f"Initializing vector store: {vector_db_type}")
        
        # Validate that the type is supported
        if vector_db_type not in VectorStoreFactory.SUPPORTED_TYPES:
            supported = ', '.join(VectorStoreFactory.SUPPORTED_TYPES.keys())
            raise ValueError(
                f"Unsupported VECTOR_DB_TYPE: {vector_db_type}. "
                f"Supported types: {supported}"
            )
        
        # Create the appropriate vector store instance
        if vector_db_type == 'PGVECTOR':
            _vector_store_instance = VectorStoreFactory._create_pgvector_store(db)
            
        elif vector_db_type == 'QDRANT':
            _vector_store_instance = VectorStoreFactory._create_qdrant_store(db)
            
        elif vector_db_type in ['PINECONE', 'WEAVIATE', 'CHROMA']:
            raise NotImplementedError(
                f"{vector_db_type} support is planned but not yet implemented. "
                f"Currently supported: PGVECTOR, QDRANT"
            )
        
        logger.info(f"Vector store initialized: {vector_db_type}")
        return _vector_store_instance
    
    @staticmethod
    def _create_pgvector_store(db) -> VectorStoreBase:
        """
        Create PGVector store instance.
        
        Args:
            db: Database object
            
        Returns:
            PGVectorStore instance
        """
        from tools.vector_stores.pgvector_store import PGVectorStore
        
        # PGVector uses the existing PostgreSQL connection
        logger.debug("Creating PGVector store with existing database connection")
        return PGVectorStore(db)
    
    @staticmethod
    def _create_qdrant_store(db) -> VectorStoreBase:
        """
        Create Qdrant store instance.
        
        Args:
            db: Database object (may not be used, but kept for consistency)
            
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
            url=config.QDRANT_URL,
            api_key=config.QDRANT_API_KEY,
            prefer_grpc=config.QDRANT_PREFER_GRPC
        )
    
    @staticmethod
    def reset():
        """
        Reset the singleton instance.
        
        This is useful for testing or when you need to reinitialize
        the vector store with different configuration.
        """
        global _vector_store_instance
        _vector_store_instance = None
        logger.info("Vector store instance reset")
    
    @staticmethod
    def get_current_type() -> str:
        """
        Get the currently configured vector database type.
        
        Returns:
            String indicating the vector DB type (e.g., 'PGVECTOR', 'QDRANT')
        """
        return config.VECTOR_DB_TYPE
    
    @staticmethod
    def get_supported_types() -> dict:
        """
        Get dictionary of supported vector database types.
        
        Returns:
            Dictionary mapping type codes to descriptions
        """
        return VectorStoreFactory.SUPPORTED_TYPES.copy()


def get_vector_store(db) -> VectorStoreBase:
    """
    Convenience function to get the vector store instance.
    
    This is the main entry point for code that needs a vector store.
    
    Args:
        db: Database object
        
    Returns:
        VectorStoreBase implementation instance
        
    Example:
        >>> from tools.vector_store_factory import get_vector_store
        >>> from db.database import db
        >>> vector_store = get_vector_store(db)
        >>> vector_store.index_documents('my_collection', documents)
    """
    return VectorStoreFactory.create_vector_store(db)
