from langchain_openai import OpenAIEmbeddings
from langchain_community.embeddings import HuggingFaceEmbeddings
from app.model.embedding_service import EmbeddingProvider
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
        return HuggingFaceEmbeddings(
            model_name=embedding_service.name,
            encode_kwargs={'normalize_embeddings': True},
            client_kwargs={
                "verify": False,
                "headers": {
                    "Authorization": f"Bearer {embedding_service.api_key}"
                }
            }
        )
    else:
        raise ValueError(f"Unsupported embedding provider: {embedding_service.provider}")
