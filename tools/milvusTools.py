from langchain_community.vectorstores.milvus import Milvus
from langchain_openai import OpenAIEmbeddings
from langchain_community.document_loaders import PyPDFLoader
from langchain.text_splitter import CharacterTextSplitter
from model.resource import Resource
import os


REPO_BASE_FOLDER = 'data/repositories'
COLLECTION_PREFIX = 'collection_'

def index_resource(resource):
    loader = PyPDFLoader(os.path.join(REPO_BASE_FOLDER, str(resource.repository_id), resource.uri), extract_images=False)
    pages = loader.load()
    text_splitter = CharacterTextSplitter(chunk_size=10, chunk_overlap=0)
    docs = text_splitter.split_documents(pages)
    embeddings = OpenAIEmbeddings()
    collection_name = COLLECTION_PREFIX + str(resource.repository_id)  
    milvus = Milvus( embeddings,  collection_name=collection_name , connection_args={"host": "localhost", "port": "19530"}, auto_id=True)
    milvus.add_documents(docs)

def search_similar_resources(repository_id, embed, RESULTS=5):
    collection_name = COLLECTION_PREFIX + str(repository_id)  
    embeddings = OpenAIEmbeddings()
    milvus = Milvus( embeddings,  collection_name=collection_name , connection_args={"host": "localhost", "port": "19530"}, auto_id=True)
    return milvus.similarity_search_with_score_by_vector(embed, RESULTS)

    




