import logging
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic
from langchain_ollama import ChatOllama
from langchain_core.output_parsers import StrOutputParser, JsonOutputParser
from langchain_core.retrievers import BaseRetriever
from langchain_mistralai import ChatMistralAI
from mistralai import Mistral
from langchain_azure_ai.chat_models import AzureAIChatCompletionsModel

from models.ai_service import ProviderEnum
from tools.pgVectorTools import PGVectorTools
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

# Initialize pgVectorTools lazily when needed
_pgVectorTools = None

def get_pgVectorTools():
    """Get or create PGVectorTools instance"""
    global _pgVectorTools
    if _pgVectorTools is None:
        from db.database import db
        _pgVectorTools = PGVectorTools(db)
    return _pgVectorTools

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
    
    if ai_service.provider == ProviderEnum.OpenAI.value:
        return ChatOpenAI(model=ai_service.description, temperature=temperature, api_key=ai_service.api_key, base_url=ai_service.endpoint if ai_service.endpoint else None)
    if ai_service.provider == ProviderEnum.Anthropic.value:
        return ChatAnthropic(model=ai_service.description, temperature=temperature, api_key=ai_service.api_key)
    if ai_service.provider == ProviderEnum.MistralAI.value:
        if is_vision:
            mistral_client = Mistral(api_key=ai_service.api_key)
            return MistralWrapper(client=mistral_client, model_name=ai_service.description)
        return ChatMistralAI(model=ai_service.description, temperature=temperature, api_key=ai_service.api_key)
    if ai_service.provider == ProviderEnum.Custom.value:
        service = ChatOllama(
            model=ai_service.description, 
            temperature=temperature,
            base_url=ai_service.endpoint,
            client_kwargs={
                "verify": False,
                "headers": {
                    "Authorization": f"Bearer {ai_service.api_key}"
                }
            }
        )
        logger.info(f"Service: {service}")
        return service
    if ai_service.provider == ProviderEnum.Azure.value:
        return AzureAIChatCompletionsModel(
            model=ai_service.description,
            temperature=temperature,
            credential=ai_service.api_key,
            endpoint=ai_service.endpoint,
            api_version=ai_service.api_version
        )
        
    raise ValueError(f"Proveedor de modelo no soportado: {ai_service.provider}")

class MistralWrapper:
    def __init__(self, client, model_name):
        self.client = client
        self.model_name = model_name

class VoidRetriever(BaseRetriever):
    
    def _get_relevant_documents(self, query: str) -> List[Document]:
        return []

    async def _aget_relevant_documents(self, query: str) -> List[Document]:
        return []

