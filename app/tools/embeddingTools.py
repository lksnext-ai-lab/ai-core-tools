from langchain_openai import OpenAIEmbeddings
from huggingface_hub import InferenceClient
from app.model.embedding_service import EmbeddingProvider

class HuggingFaceEmbeddingsAdapter:
    def __init__(self, client):
        self.client = client
        
    def embed_query(self, text):
        return self.client.feature_extraction(text).tolist()
        
    def embed_documents(self, documents):
        return [self.embed_query(doc) for doc in documents]

def get_embeddings_model(embedding_service):
    """Returns the appropriate embeddings model based on the service configuration"""
    if embedding_service is None:
        raise ValueError("No embedding service provided")

    if embedding_service.provider == EmbeddingProvider.OpenAI.value:
        return OpenAIEmbeddings(
            model=embedding_service.name,
            openai_api_key=embedding_service.api_key
        )
    elif embedding_service.provider == EmbeddingProvider.Custom.value:
        client = InferenceClient(
            model=embedding_service.endpoint,
            api_key=embedding_service.api_key
        )
        return HuggingFaceEmbeddingsAdapter(client)
    else:
        raise ValueError(f"Unsupported embedding provider: {embedding_service.provider}")
