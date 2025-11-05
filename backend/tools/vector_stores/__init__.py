"""
Vector stores package.

This package contains implementations of the VectorStoreBase interface
for different vector database backends.
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .pgvector_store import PGVectorStore

__all__ = ['PGVectorStore']
