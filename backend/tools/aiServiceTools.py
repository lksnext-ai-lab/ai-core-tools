import base64
import json
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
from typing import List, Any, Optional
from langchain_core.documents import Document
from tools.embeddingTools import get_embeddings_model
from tools.execution_profiles import (
    ExecutionProfile,
    RuntimeConfigBuilder,
    build_runtime_kwargs,
)
from utils.logger import get_logger

load_dotenv()

logger = get_logger(__name__)

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

def _resolve_execution_profile(ai_service, agent, is_vision=False, override_profile=None) -> "ExecutionProfile":
    """Resolve the execution profile for an LLM build.

    Resolution order:
      1. Per-request override (if provided)
      2. Agent-level override (if set)
      3. AI service default
      4. Provider default
    """
    if override_profile is not None:
        try:
            return ExecutionProfile(int(override_profile))
        except ValueError:
            pass

    agent_profile = getattr(agent, 'execution_profile', None) if agent is not None else None
    if agent_profile is not None:
        try:
            return ExecutionProfile(agent_profile)
        except ValueError:
            pass

    service_profile = getattr(ai_service, 'execution_profile', 1)
    if service_profile is not None:
        try:
            return ExecutionProfile(int(service_profile))
        except ValueError:
            pass

    return ExecutionProfile.BALANCED


def create_llm_from_service(
    ai_service,
    temperature=0,
    is_vision=False,
    agent: Optional[Any] = None,
    override_execution_profile: Optional[int] = None,
    override_temperature: Optional[float] = None,
) -> Any:
    """
    Create an LLM instance from an AIService model, threaded with
    execution-profile parameters.

    Args:
        ai_service: AIService model instance.
        temperature: float.
        is_vision: boolean (used for Mistral vision path).
        agent: optional Agent that may override the service profile.
        override_execution_profile: optional per-request execution profile override.
        override_temperature: optional per-request temperature override.
    """
    provider_builders = {
        ProviderEnum.OpenAI.value: lambda: _build_openai_llm(ai_service, temperature),
        ProviderEnum.Anthropic.value: lambda: _build_anthropic_llm(ai_service, temperature),
        ProviderEnum.MistralAI.value: lambda: _build_mistral_llm(ai_service, temperature, is_vision),
        ProviderEnum.Custom.value: lambda: _build_custom_llm(ai_service, temperature),
        ProviderEnum.Azure.value: lambda: _build_azure_llm(ai_service, temperature),
        ProviderEnum.Google.value: lambda: _build_google_llm(ai_service, temperature),
        ProviderEnum.GoogleCloud.value: lambda: _build_google_cloud_llm(ai_service, temperature),
        ProviderEnum.OpenRouter.value: lambda: _build_openrouter_llm(ai_service, temperature),
        ProviderEnum.Bedrock.value: lambda: _build_bedrock_llm(ai_service, temperature),
    }
    # Determine which temperature to use: per-request override > agent value
    effective_temperature = temperature
    if override_temperature is not None:
        effective_temperature = override_temperature

    execution_profile = _resolve_execution_profile(ai_service, agent, is_vision, override_profile=override_execution_profile)

    # Handle case where provider might be an Enum object instead of string
    provider = ai_service.provider
    if hasattr(provider, 'value'):
        provider = provider.value

    model_id = ai_service.description or ""

    # Build runtime config from provider + model + profile
    runtime_config = RuntimeConfigBuilder.build(
        provider=provider,
        model_id=model_id,
        execution_profile=execution_profile,
    )

    # Determine temperature — may be disabled by the runtime config
    temp = effective_temperature if not runtime_config.disable_temperature else None

    # If the model requires a specific temperature value (e.g. 1.0) regardless
    # of what the agent or user configured, override here.
    if runtime_config.force_temperature is not None:
        temp = runtime_config.force_temperature

    # Dispatch to provider-specific builder with runtime kwargs
    provider_builders = {
        ProviderEnum.OpenAI.value: lambda: _build_openai_llm(ai_service, temp, runtime_config),
        ProviderEnum.Anthropic.value: lambda: _build_anthropic_llm(ai_service, temp, runtime_config),
        ProviderEnum.MistralAI.value: lambda: _build_mistral_llm(ai_service, temp, is_vision, runtime_config),
        ProviderEnum.Custom.value: lambda: _build_custom_llm(ai_service, temp, runtime_config),
        ProviderEnum.Azure.value: lambda: _build_azure_llm(ai_service, temp, runtime_config),
        ProviderEnum.Google.value: lambda: _build_google_llm(ai_service, temp, runtime_config),
        ProviderEnum.GoogleCloud.value: lambda: _build_google_cloud_llm(ai_service, temp, runtime_config),
        ProviderEnum.OpenRouter.value: lambda: _build_openrouter_llm(ai_service, temp, runtime_config),
    }

    builder = provider_builders.get(provider)
    if builder is None:
        raise ValueError(f"Proveedor de modelo no soportado: {provider}")

    return builder()


def get_llm(agent, is_vision=False, override_temperature: Optional[float] = None):
    """
    Función base para obtener cualquier modelo LLM
    Args:
        agent: Agent object with model configuration
        is_vision: Boolean que indica si es un modelo de visión
        override_temperature: optional per-request temperature override
    """
    if is_vision:
        ai_service = agent.vision_service_rel
    else:
        ai_service = agent.ai_service
        
    if ai_service is None:
        return None
    
    # Get temperature from agent, default to DEFAULT_AGENT_TEMPERATURE if not set
    from models.agent import DEFAULT_AGENT_TEMPERATURE
    temperature = override_temperature if override_temperature is not None else getattr(agent, 'temperature', DEFAULT_AGENT_TEMPERATURE)

    return create_llm_from_service(
        ai_service, temperature, is_vision, agent=agent,
        override_temperature=override_temperature,
    )

class MistralWrapper:
    def __init__(self, client, model_name):
        self.client = client
        self.model_name = model_name

class VoidRetriever(BaseRetriever):
    
    def _get_relevant_documents(self, query: str) -> "List[Document]":
        return []

    async def _aget_relevant_documents(self, query: str) -> "List[Document]":
        return []


def _build_openai_llm(ai_service, temperature, runtime_config):
    base_url = ai_service.endpoint if ai_service.endpoint else None

    kwargs = {
        "model": ai_service.description,
        "api_key": ai_service.api_key,
        "base_url": base_url,
    }

    # Temperature (may be skipped by runtime config)
    if temperature is not None:
        kwargs["temperature"] = temperature

    # Add runtime reasoning kwargs
    kwargs.update(build_runtime_kwargs(runtime_config))

    return ChatOpenAI(**kwargs)


# OpenRouter session-level defaults — configurable later via env vars.
_OPENROUTER_DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"


def _build_openrouter_llm(ai_service, temperature, runtime_config):
    """Build a ChatOpenAI instance pointed at OpenRouter's API.

    OpenRouter speaks the OpenAI chat completions protocol, so we reuse
    ChatOpenAI with a different base_url. The description field stores
    the full model identifier (e.g. ``openai/gpt-4o``).

    Attribution headers (HTTP-Referer, X-Title) identify MattinAI on
    the OpenRouter platform.
    """
    base_url = (ai_service.endpoint or _OPENROUTER_DEFAULT_BASE_URL).rstrip("/")

    default_headers = {
        "HTTP-Referer": "https://github.com/lksnext-ai-lab/ai-core-tools",
        "X-Title": "MattinAI",
    }

    kwargs = {
        "model": ai_service.description,
        "api_key": ai_service.api_key,
        "base_url": base_url,
        "default_headers": default_headers,
    }

    if temperature is not None:
        kwargs["temperature"] = temperature

    kwargs.update(build_runtime_kwargs(runtime_config))

    return ChatOpenAI(**kwargs)


def _build_anthropic_llm(ai_service, temperature, runtime_config):
    kwargs = {
        "model": ai_service.description,
        "api_key": ai_service.api_key,
    }

    if temperature is not None:
        kwargs["temperature"] = temperature

    kwargs.update(build_runtime_kwargs(runtime_config))

    return ChatAnthropic(**kwargs)


def _build_mistral_llm(ai_service, temperature, is_vision, runtime_config):
    if is_vision:
        mistral_client = Mistral(api_key=ai_service.api_key)
        return MistralWrapper(client=mistral_client, model_name=ai_service.description)

    kwargs = {
        "model": ai_service.description,
        "api_key": ai_service.api_key,
    }

    if temperature is not None:
        kwargs["temperature"] = temperature

    kwargs.update(build_runtime_kwargs(runtime_config))

    return ChatMistralAI(**kwargs)


def build_ollama_auth_headers(api_key: Optional[str], endpoint: Optional[str]) -> dict:
    """Build auth headers for an Ollama-protocol endpoint.

    Self-hosted Ollama instances are commonly placed behind a reverse
    proxy. Two authentication patterns are supported:

    * ``Authorization: Bearer <api_key>`` when an API key is provided.
    * ``Authorization: Basic <base64(user:pass)>`` when the endpoint URL
      embeds basic-auth credentials. Basic auth takes precedence — it
      mirrors the behaviour the runtime has had since this provider was
      introduced.

    Used both by :func:`_build_custom_llm` (runtime) and by the listing
    adapter in :mod:`tools.ai.provider_model_clients` so the two paths
    cannot drift out of sync.
    """
    headers = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    if endpoint:
        parsed = urlparse(endpoint)
        if parsed.username and parsed.password:
            credentials = f"{parsed.username}:{parsed.password}"
            encoded = base64.b64encode(credentials.encode()).decode()
            headers["Authorization"] = f"Basic {encoded}"
    return headers


def _build_custom_llm(ai_service, temperature, runtime_config):
    client_kwargs = {"verify": False}
    headers = build_ollama_auth_headers(ai_service.api_key, ai_service.endpoint)
    if headers:
        client_kwargs["headers"] = headers

    kwargs = {
        "model": ai_service.description,
        "client_kwargs": client_kwargs,
    }

    if temperature is not None:
        kwargs["temperature"] = temperature

    if ai_service.endpoint:
        kwargs["base_url"] = ai_service.endpoint

    kwargs.update(build_runtime_kwargs(runtime_config))

    return ChatOllama(**kwargs)


def _build_azure_llm(ai_service, temperature, runtime_config):
    kwargs = {
        "model": ai_service.description,
        "credential": ai_service.api_key,
        "endpoint": ai_service.endpoint,
        "api_version": ai_service.api_version,
    }

    if temperature is not None:
        kwargs["temperature"] = temperature

    kwargs.update(build_runtime_kwargs(runtime_config))

    return AzureAIChatCompletionsModel(**kwargs)


def _build_bedrock_llm(ai_service, temperature):
    from langchain_aws import ChatBedrockConverse

    from tools.aws_bedrock_utils import resolve_bedrock_credentials

    creds = resolve_bedrock_credentials(ai_service)
    bedrock_kwargs = {
        "model": ai_service.description,
        "temperature": temperature,
        **creds,
    }

    endpoint_raw = (ai_service.endpoint or "").strip()
    if endpoint_raw:
        bedrock_kwargs["endpoint_url"] = endpoint_raw

    return ChatBedrockConverse(**bedrock_kwargs)


_DEFAULT_GOOGLE_HOST = "generativelanguage.googleapis.com"


def _resolve_google_client_options(endpoint_raw, service_name):
    """Return client_options dict for a custom Google endpoint, or None to use the library default.

    The new google-genai REST client (v1.x) requires api_endpoint to include https://,
    otherwise httpx raises 'Request URL is missing an http:// or https:// protocol'.
    The default endpoint is skipped entirely — the library already knows it.
    """
    parsed = urlparse(endpoint_raw if "://" in endpoint_raw else f"https://{endpoint_raw}")
    host = parsed.netloc or parsed.path
    normalized_host = host.lower()

    is_google = "googleapis.com" in normalized_host or "googleusercontent.com" in normalized_host
    if not is_google:
        logger.warning(
            "Ignoring non-Google endpoint '%s' configured for provider Google on service '%s'",
            endpoint_raw,
            service_name,
        )
        return None

    if normalized_host == _DEFAULT_GOOGLE_HOST:
        return None  # Default endpoint — no override needed.

    if parsed.path not in ("", "/") and parsed.netloc:
        logger.warning(
            "Ignoring path '%s' in Google endpoint '%s'; only host is supported",
            parsed.path,
            endpoint_raw,
        )
    return {"api_endpoint": f"https://{host}"}


def _build_google_llm(ai_service, temperature, runtime_config):
    google_kwargs = {
        "model": ai_service.description,
        "api_key": ai_service.api_key,
    }

    if temperature is not None:
        google_kwargs["temperature"] = temperature

    endpoint_raw = (ai_service.endpoint or "").strip()
    if endpoint_raw:
        client_options = _resolve_google_client_options(
            endpoint_raw, getattr(ai_service, "name", "unknown")
        )
        if client_options:
            google_kwargs["client_options"] = client_options

    google_kwargs.update(build_runtime_kwargs(runtime_config))

    return ChatGoogleGenerativeAI(**google_kwargs)


def _build_google_cloud_llm(ai_service, temperature, runtime_config):
    import json
    import os
    from google.oauth2 import service_account

    project_id = (ai_service.endpoint or "").strip()
    location = (getattr(ai_service, 'api_version', None) or "").strip() or "europe-west1"
    api_key_raw = (ai_service.api_key or "").strip()

    if not api_key_raw:
        raise ValueError("Service Account JSON is required for Google Cloud provider.")

    sa_info = json.loads(api_key_raw)

    os.environ.pop("GOOGLE_API_KEY", None)
    os.environ.pop("GEMINI_API_KEY", None)

    credentials = service_account.Credentials.from_service_account_info(
        sa_info,
        scopes=["https://www.googleapis.com/auth/cloud-platform"],
    )

    kwargs = {
        "model": ai_service.description,
        "credentials": credentials,
        "project": project_id,
        "location": location,
        "vertexai": True,
    }

    if temperature is not None:
        kwargs["temperature"] = temperature

    kwargs.update(build_runtime_kwargs(runtime_config))

    return ChatGoogleGenerativeAI(**kwargs)
