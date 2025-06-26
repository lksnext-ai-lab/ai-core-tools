from langchain_openai import OpenAIEmbeddings
from langchain_ollama import OllamaEmbeddings
from langchain_mistralai import MistralAIEmbeddings
from langchain_azure_ai.embeddings import AzureAIEmbeddingsModel
from huggingface_hub import InferenceClient
from model.embedding_service import EmbeddingProvider
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class HuggingFaceEmbeddingsAdapter:
    def __init__(self, client):
        self.client = client
        
    def embed_query(self, text):
        result = self.client.feature_extraction(text).tolist()
        return result[0] if isinstance(result[0], list) else result
        
    def embed_documents(self, documents):
        return [self.embed_query(doc) for doc in documents]

def get_embeddings_model(embedding_service):
    """Returns the appropriate embeddings model based on the service configuration"""
    if embedding_service is None:
        raise ValueError("No embedding service provided")
    
    logger.info(f"Proveedor {embedding_service.provider}")

    if embedding_service.provider == EmbeddingProvider.OpenAI.value:
        return OpenAIEmbeddings(
            model=embedding_service.name,
            api_key=embedding_service.api_key
        )
    
    elif embedding_service.provider == EmbeddingProvider.MistralAI.value:
        return MistralAIEmbeddings(
            model=embedding_service.name,
            api_key=embedding_service.api_key
        )
    
    elif embedding_service.provider == EmbeddingProvider.Custom.value:
        client = InferenceClient(
            model=embedding_service.name if embedding_service.name else None,
            base_url=embedding_service.endpoint,
            headers={
                "Authorization": f"Bearer {embedding_service.api_key}"
            },
        )
        return HuggingFaceEmbeddingsAdapter(client)
    elif embedding_service.provider == EmbeddingProvider.Ollama.value:
        logger.info("Entro bien en ollama")
        return OllamaEmbeddings(
            model=embedding_service.name,
            base_url=embedding_service.endpoint,
            client_kwargs={
                "verify": False,
                "headers": {
                    "Authorization": f"Bearer {embedding_service.api_key}"
                }
            }
        )
    elif embedding_service.provider == EmbeddingProvider.Azure.value:
        return AzureAIEmbeddingsModel(
            model_name=embedding_service.name,
            api_version=embedding_service.api_version or "2024-02-15-preview",
            credential=embedding_service.api_key,
            endpoint=embedding_service.endpoint
        )

    else:
        raise ValueError(f"Unsupported embedding provider: {embedding_service.provider}")
