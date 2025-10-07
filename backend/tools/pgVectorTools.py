import os
import warnings, deprecation

import numpy as np
from sqlalchemy.orm import sessionmaker

from langchain_openai import OpenAIEmbeddings
from langchain_community.document_loaders.pdf import PyPDFLoader
from langchain.text_splitter import CharacterTextSplitter
from langchain_postgres.vectorstores import PGVector
from langchain_community.embeddings import HuggingFaceEmbeddings
from models.embedding_service import EmbeddingProvider
from tools.embeddingTools import get_embeddings_model

from models.resource import Resource
from typing import Optional
from langchain.schema import Document
from typing import List
# from extensions import async_engine  # TODO: Fix async engine import

REPO_BASE_FOLDER = os.path.abspath(os.getenv("REPO_BASE_FOLDER"))
#TODO: pgVector should not know abot silos
COLLECTION_PREFIX = 'silo_'

class PGVectorTools:
    def __init__(self, db):
        """Initializes the PGVectorTools with a SQLAlchemy engine."""
        self.Session = db.session
        self.db = db
        # Use async engine for vector operations (required for async retriever in LangGraph)
        self._async_engine = getattr(db, '_async_engine', None)    

    @deprecation.deprecated(
        deprecated_in="0.1.0",
        current_version="0.1.0",
        details="This method is deprecated and will be removed in a future version. Use the 'index_documents' method instead."
    )
    def index_resource(self, resource):
        """Indexes a resource by loading its content, splitting it into chunks, and adding it to the pgvector table."""
        
        loader = PyPDFLoader(os.path.join(REPO_BASE_FOLDER, str(resource.repository_id), resource.uri), extract_images=False)
        pages = loader.load()
        text_splitter = CharacterTextSplitter(chunk_size=10, chunk_overlap=0)
        docs = text_splitter.split_documents(pages)

        for doc in docs:
            doc.metadata["repository_id"] = resource.repository_id
            doc.metadata["resource_id"] = resource.resource_id
            doc.metadata["silo_id"] = resource.repository.silo_id


        vector_store = PGVector(
            embeddings=get_embeddings_model(resource.embedding_service),
            collection_name=COLLECTION_PREFIX + str(resource.repository.silo_id),
            connection=self.db.engine,
            use_jsonb=True,
        )
        vector_store.add_documents(docs)

    def index_documents(self, collection_name: str, documents: list[Document], embedding_service=None):
        """Indexes a list of documents in the pgvector collection using langchain vector store."""
        vector_store = PGVector(
            embeddings=get_embeddings_model(embedding_service),
            collection_name=collection_name,
            connection=self.db.engine,
            use_jsonb=True,
        )
        vector_store.add_documents(documents)

    @deprecation.deprecated(
        deprecated_in="0.1.0",
        current_version="0.1.0",
        details="This method is deprecated and will be removed in a future version. Use the 'delete_documents' method instead."
    )
    def delete_resource(self, resource):
        """Deletes a resource from the pgvector table using langchain vector store."""
        vector_store = PGVector(
            embeddings=get_embeddings_model(resource.embedding_service),
            collection_name=COLLECTION_PREFIX + str(resource.repository.silo_id),
            connection=self.db.engine,
            use_jsonb=True,
        )
        results = vector_store.similarity_search(
            "", k=1000, filter={"resource_id": {"$eq": resource.resource_id}}
        )
        print(results)
        ids_array = [doc.id for doc in results]
        print(ids_array)
        
        vector_store.delete(ids=ids_array)

    def delete_documents(self, collection_name: str, ids, embedding_service=None):
        """Deletes documents from the pgvector collection using langchain vector store."""
        vector_store = PGVector(
            embeddings=get_embeddings_model(embedding_service),
            collection_name=collection_name,
            connection=self.db.engine,
            use_jsonb=True,
        )
        if isinstance(ids, list):
            vector_store.delete(ids=ids)
        else:
            #TODO: for deleting docs embedding_service should not be needed. In fact, if api key  fails we can not delete docs.
            results = vector_store.similarity_search(
                "", k=1000, filter=ids
            )
            ids_array = [doc.id for doc in results]
            vector_store.delete(ids=ids_array)

    def delete_collection(self, collection_name : str, embedding_service):
        """Deletes a collection from the pgvector database."""
        vector_store = PGVector(
            embeddings=get_embeddings_model(embedding_service),
            collection_name=collection_name,
            connection=self.db.engine,
        )
        vector_store.delete_collection()
        
    @deprecation.deprecated(
        deprecated_in="0.1.0",
        current_version="0.1.0",
        details="This method is deprecated and will be removed in a future version. Use the 'search_similar_documents' method instead."
    )
    def search_similar_resources(self, repository : str, embed, RESULTS=5):
        """Searches for similar resources in the pgvector table using langchain vector store."""
        vector_store = PGVector(
            embeddings=get_embeddings_model(None),
            collection_name=COLLECTION_PREFIX + str(repository.silo_id),
            connection=self.db.engine,
            use_jsonb=True,
        )
        results = vector_store.similarity_search_by_vector(
            embedding=embed,
            k=RESULTS
        )
        return results
    
    def search_similar_documents(self, collection_name: str, query: str, embedding_service=None, filter_metadata: Optional[dict] = None, RESULTS=5):
        """Searches for similar documents using the configured embedding service"""
        vector_store = PGVector(
            embeddings=get_embeddings_model(embedding_service),
            collection_name=collection_name,
            connection=self.db.engine,
            use_jsonb=True,
        )
        
        # Handle empty queries by returning documents with just metadata filtering
        if not query or (isinstance(query, str) and not query.strip()):
            # For empty queries, use similarity_search without query to get documents with metadata filtering
            results_with_scores = vector_store.similarity_search_with_score(
                " ",  # Use a space as minimal query
                k=RESULTS,
                filter=filter_metadata
            )
        elif isinstance(query, (list, np.ndarray)):
            # Si recibimos directamente el embedding, lo usamos
            results_with_scores = vector_store.similarity_search_with_score_by_vector(
                embedding=query,
                k=RESULTS,
                filter=filter_metadata
            )
        else:
            # Si recibimos texto, hacemos la búsqueda normal con scores
            results_with_scores = vector_store.similarity_search_with_score(
                query,
                k=RESULTS,
                filter=filter_metadata
            )
        
        # Convert the results to include score in metadata
        results = []
        for doc, score in results_with_scores:
            # Create a new Document with score in metadata instead of as attribute
            new_doc = Document(
                page_content=doc.page_content,
                metadata={**doc.metadata, '_score': score}
            )
            results.append(new_doc)
            
        return results
    
    def get_pgvector_retriever(self, collection_name: str, embedding_service=None, search_params=None, use_async=False, **kwargs):
        """Returns a retriever object for the pgvector collection.
        
        Args:
            collection_name: Name of the collection
            embedding_service: Embedding service to use
            search_params: Optional search parameters
            use_async: If True, uses async engine for async operations (e.g., in LangGraph with ainvoke)
            **kwargs: Additional arguments to pass to as_retriever
        """
        # Use async engine if requested and available, otherwise fall back to sync engine
        connection = self._async_engine if (use_async and self._async_engine) else self.db.engine
        
        vector_store = PGVector(
            embeddings=get_embeddings_model(embedding_service),
            collection_name=collection_name,
            connection=connection,
            use_jsonb=True,
        )
        
        if search_params is not None:
            return vector_store.as_retriever(search_kwargs=search_params, **kwargs)
        return vector_store.as_retriever(**kwargs)


