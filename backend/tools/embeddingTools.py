from langchain_openai import OpenAIEmbeddings
from langchain_ollama import OllamaEmbeddings
from langchain_mistralai import MistralAIEmbeddings
from langchain_azure_ai.embeddings import AzureAIEmbeddingsModel
from huggingface_hub import InferenceClient
from models.embedding_service import EmbeddingProvider
from utils.logger import get_logger
import json
import os

logger = get_logger(__name__)

class HuggingFaceEmbeddingsAdapter:
    def __init__(self, client):
        self.client = client
        
    def embed_query(self, text):
        result = self.client.feature_extraction(text).tolist()
        return result[0] if isinstance(result[0], list) else result
        
    def embed_documents(self, documents):
        return [self.embed_query(doc) for doc in documents]


def _build_openai_embeddings(embedding_service, model_id):
    return OpenAIEmbeddings(
        model=model_id,
        api_key=embedding_service.api_key
    )


def _build_mistral_embeddings(embedding_service, model_id):
    return MistralAIEmbeddings(
        model=model_id,
        api_key=embedding_service.api_key
    )


def _build_huggingface_embeddings(embedding_service, model_id):
    client = InferenceClient(
        model=embedding_service.endpoint,
        api_key=embedding_service.api_key
    )
    return HuggingFaceEmbeddingsAdapter(client)


def _build_ollama_embeddings(embedding_service, model_id):
    return OllamaEmbeddings(
        model=model_id,
        base_url=embedding_service.endpoint,
        client_kwargs={
            "verify": False,
            "headers": {
                "Authorization": f"Bearer {embedding_service.api_key}"
            }
        }
    )


def _build_azure_embeddings(embedding_service, model_id):
    return AzureAIEmbeddingsModel(
        model_name=model_id,
        api_version=embedding_service.api_version or "2024-02-15-preview",
        credential=embedding_service.api_key,
        endpoint=embedding_service.endpoint
    )


def _build_google_embeddings(embedding_service, model_id):
    from langchain_google_genai import GoogleGenerativeAIEmbeddings

    return GoogleGenerativeAIEmbeddings(
        model=model_id,
        api_key=embedding_service.api_key,
    )


def _build_google_cloud_embeddings(embedding_service, model_id):
    from google.oauth2 import service_account
    from langchain_google_genai import GoogleGenerativeAIEmbeddings

    project_id = (embedding_service.endpoint or "").strip()
    location = (getattr(embedding_service, "api_version", None) or "").strip() or "europe-west1"
    api_key_raw = (embedding_service.api_key or "").strip()

    if not api_key_raw:
        raise ValueError("Service Account JSON is required for Google Cloud provider.")
    if not project_id:
        raise ValueError("Project ID is required for Google Cloud provider.")

    service_account_info = json.loads(api_key_raw)

    os.environ.pop("GOOGLE_API_KEY", None)
    os.environ.pop("GEMINI_API_KEY", None)

    credentials = service_account.Credentials.from_service_account_info(
        service_account_info,
        scopes=["https://www.googleapis.com/auth/cloud-platform"],
    )

    return GoogleGenerativeAIEmbeddings(
        model=model_id,
        credentials=credentials,
        project=project_id,
        location=location,
        vertexai=True,
    )


def _build_bedrock_embeddings(embedding_service, model_id):
    from langchain_aws import BedrockEmbeddings

    from tools.aws_bedrock_utils import resolve_bedrock_credentials

    creds = resolve_bedrock_credentials(embedding_service)
    kwargs = {"model_id": model_id, **creds}

    endpoint_raw = (embedding_service.endpoint or "").strip()
    if endpoint_raw:
        kwargs["endpoint_url"] = endpoint_raw

    return BedrockEmbeddings(**kwargs)


_EMBEDDING_BUILDERS = {
    EmbeddingProvider.OpenAI.value: _build_openai_embeddings,
    EmbeddingProvider.MistralAI.value: _build_mistral_embeddings,
    EmbeddingProvider.Custom.value: _build_huggingface_embeddings,
    EmbeddingProvider.Ollama.value: _build_ollama_embeddings,
    EmbeddingProvider.Azure.value: _build_azure_embeddings,
    EmbeddingProvider.Google.value: _build_google_embeddings,
    EmbeddingProvider.GoogleCloud.value: _build_google_cloud_embeddings,
    EmbeddingProvider.Bedrock.value: _build_bedrock_embeddings,
}


def get_embeddings_model(embedding_service):
    """Returns the appropriate embeddings model based on the service configuration.

    Field convention (must match AIService): ``description`` holds the model
    identifier expected by the upstream API (e.g. ``"text-embedding-3-large"``)
    while ``name`` is the human-readable label shown in the UI.
    """
    if embedding_service is None:
        raise ValueError("No embedding service provided")

    logger.info(f"Proveedor {embedding_service.provider}")

    model_id = embedding_service.description

    builder = _EMBEDDING_BUILDERS.get(embedding_service.provider)
    if builder is None:
        raise ValueError(f"Unsupported embedding provider: {embedding_service.provider}")
    return builder(embedding_service, model_id)
