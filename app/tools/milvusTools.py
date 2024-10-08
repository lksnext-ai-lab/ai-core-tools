from langchain_community.vectorstores.milvus import Milvus
from langchain_openai import OpenAIEmbeddings
from langchain_community.document_loaders.pdf import PyPDFLoader
from langchain.text_splitter import CharacterTextSplitter
from model.resource import Resource
import os


REPO_BASE_FOLDER = os.getenv("REPO_BASE_FOLDER")
COLLECTION_PREFIX = 'collection_'
HOST = os.getenv("MILVUS_HOST", "localhost")
PORT = os.getenv("MILVUS_PORT", 19530)

def create_milvus_instance(repository_id):
    embeddings = OpenAIEmbeddings()
    collection_name = COLLECTION_PREFIX + str(repository_id)  
    return Milvus(embeddings, collection_name=collection_name, connection_args={"host": HOST, "port": PORT}, auto_id=True)


def index_resource(resource):
    """Indexes a resource by loading its content, splitting it into chunks, and adding it to a Milvus collection."""
    loader = PyPDFLoader(os.path.join(REPO_BASE_FOLDER, str(resource.repository_id), resource.uri), extract_images=False)
    pages = loader.load()
    text_splitter = CharacterTextSplitter(chunk_size=10, chunk_overlap=0)
    docs = text_splitter.split_documents(pages)
    milvus = create_milvus_instance(resource.repository_id)
    milvus.add_documents(docs)

def delete_resource(resource):
    """Deletes a resource from a Milvus collection based on its source."""
    milvus = create_milvus_instance(resource.repository_id)
    expr = f"source == '{REPO_BASE_FOLDER}/{resource.repository_id}/{resource.uri}'"
    milvus.delete(expr=expr)

def search_similar_resources(repository_id, embed, RESULTS=5):
    """Searches for similar resources in a Milvus collection based on an embedding."""
    milvus = create_milvus_instance(repository_id)
    return milvus.similarity_search_with_score_by_vector(embed, RESULTS)

def get_milvus_retriever(repository_id):
    milvus = create_milvus_instance(repository_id)
    return milvus.as_retriever()

    




