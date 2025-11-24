import logging
from dotenv import load_dotenv
from langchain_anthropic import ChatAnthropic
from langchain_ollama import ChatOllama
from langchain_core.output_parsers import StrOutputParser, JsonOutputParser
from langchain_core.retrievers import BaseRetriever
from langchain_mistralai import ChatMistralAI
from mistralai import Mistral
from langchain_azure_ai.chat_models import AzureAIChatCompletionsModel
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI
from urllib.parse import urlparse

from models.ai_service import ProviderEnum
from tools.outputParserTools import get_parser_model_by_id
from typing import List
from langchain_core.documents import Document
from tools.embeddingTools import get_embeddings_model
load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize VectorStore lazily when needed

def get_embedding(text, embedding_service=None):
    """Get embeddings using the configured service"""
    embeddings = get_embeddings_model(embedding_service)
        
    return embeddings.embed_query(text)

def get_output_parser(agent):
    """Obtiene el parser apropiado basado en el output_parser_id del agente"""
    if agent.output_parser_id is None:
        return StrOutputParser()

    try:
        pydantic_model = get_parser_model_by_id(agent.output_parser_id)
        return JsonOutputParser(pydantic_object=pydantic_model)
    except Exception as e:
        print(f"Error al crear el modelo Pydantic: {str(e)}")
        return StrOutputParser()

# Legacy functions removed - now using create_agent from agentTools.py
# This provides full tool support, MCP integration, and LangSmith tracing

def get_llm(agent, is_vision=False):
    """
    Función base para obtener cualquier modelo LLM
    Args:
        agent: Agent object with model configuration
        is_vision: Boolean que indica si es un modelo de visión
    """
    if is_vision:
        ai_service = agent.vision_service_rel
    else:
        ai_service = agent.ai_service
        
    if ai_service is None:
        return None
    
    # Get temperature from agent, default to DEFAULT_AGENT_TEMPERATURE if not set
    from models.agent import DEFAULT_AGENT_TEMPERATURE
    temperature = getattr(agent, 'temperature', DEFAULT_AGENT_TEMPERATURE)

    provider_builders = {
        ProviderEnum.OpenAI.value: lambda: _build_openai_llm(ai_service, temperature),
        ProviderEnum.Anthropic.value: lambda: _build_anthropic_llm(ai_service, temperature),
        ProviderEnum.MistralAI.value: lambda: _build_mistral_llm(ai_service, temperature, is_vision),
        ProviderEnum.Custom.value: lambda: _build_custom_llm(ai_service, temperature),
        ProviderEnum.Azure.value: lambda: _build_azure_llm(ai_service, temperature),
        ProviderEnum.Google.value: lambda: _build_google_llm(ai_service, temperature),
    }

    builder = provider_builders.get(ai_service.provider)
    if builder is None:
        raise ValueError(f"Proveedor de modelo no soportado: {ai_service.provider}")

    return builder()

class MistralWrapper:
    def __init__(self, client, model_name):
        self.client = client
        self.model_name = model_name

class VoidRetriever(BaseRetriever):
    
    def _get_relevant_documents(self, query: str) -> List[Document]:
        return []

    async def _aget_relevant_documents(self, query: str) -> List[Document]:
        return []


def _build_openai_llm(ai_service, temperature):
    base_url = ai_service.endpoint if ai_service.endpoint else None
    return ChatOpenAI(
        model=ai_service.description,
        temperature=temperature,
        api_key=ai_service.api_key,
        base_url=base_url,
    )


def _build_anthropic_llm(ai_service, temperature):
    return ChatAnthropic(
        model=ai_service.description,
        temperature=temperature,
        api_key=ai_service.api_key,
    )


def _build_mistral_llm(ai_service, temperature, is_vision):
    if is_vision:
        mistral_client = Mistral(api_key=ai_service.api_key)
        return MistralWrapper(client=mistral_client, model_name=ai_service.description)
    return ChatMistralAI(
        model=ai_service.description,
        temperature=temperature,
        api_key=ai_service.api_key,
    )


def _build_custom_llm(ai_service, temperature):
    service = ChatOllama(
        model=ai_service.description,
        temperature=temperature,
        base_url=ai_service.endpoint,
        client_kwargs={
            "verify": False,
            "headers": {"Authorization": f"Bearer {ai_service.api_key}"},
        },
    )
    logger.info(f"Service: {service}")
    return service


def _build_azure_llm(ai_service, temperature):
    return AzureAIChatCompletionsModel(
        model=ai_service.description,
        temperature=temperature,
        credential=ai_service.api_key,
        endpoint=ai_service.endpoint,
        api_version=ai_service.api_version,
    )


def _build_google_llm(ai_service, temperature):
    google_kwargs = {
        "model": ai_service.description,
        "temperature": temperature,
        "google_api_key": ai_service.api_key,
    }

    endpoint_raw = (ai_service.endpoint or "").strip()
    if endpoint_raw:
        parsed = urlparse(endpoint_raw if "://" in endpoint_raw else f"https://{endpoint_raw}")
        host = parsed.netloc or parsed.path
        normalized_host = host.lower()

        if "googleapis.com" in normalized_host or "googleusercontent.com" in normalized_host:
            if parsed.path not in ("", "/") and parsed.netloc:
                logger.warning(
                    "Ignoring path '%s' in Google endpoint '%s'; only host is supported",
                    parsed.path,
                    endpoint_raw,
                )
            google_kwargs["client_options"] = {"api_endpoint": host}
        else:
            logger.warning(
                "Ignoring non-Google endpoint '%s' configured for provider Google on service '%s'",
                endpoint_raw,
                getattr(ai_service, "name", "unknown"),
            )

    return ChatGoogleGenerativeAI(**google_kwargs)

