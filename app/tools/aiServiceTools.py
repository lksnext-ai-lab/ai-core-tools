import os
import logging
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_anthropic import ChatAnthropic
from langchain_core.prompts import ChatPromptTemplate
from langchain_ollama import ChatOllama
from langchain_core.output_parsers import StrOutputParser, JsonOutputParser
from langchain_core.retrievers import BaseRetriever
from langchain.prompts.prompt import PromptTemplate
from langchain.chains.conversational_retrieval.base import ConversationalRetrievalChain
from langchain.memory import ConversationBufferMemory
from langchain_mistralai import ChatMistralAI
from mistralai import Mistral

from model.ai_service import ProviderEnum
from model.agent import Agent
from extensions import db
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

pgVectorTools = PGVectorTools(db)

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

def invoke(agent, input):
    print('AGENT ' + agent.name)
    
    model = getLLM(agent)
    if model is None:
        raise ValueError("No se pudo inicializar el modelo para el agente")
        
    output_parser = get_output_parser(agent)
    if agent.output_parser_id is None:
        format_instructions = ""
    else:
        format_instructions = output_parser.get_format_instructions()
        format_instructions = format_instructions.replace('{', '{{').replace('}', '}}')

    system_prompt = agent.system_prompt
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", system_prompt),
        ("system", "<output_format_instructions>" + format_instructions + "</output_format_instructions>"),
        ("human", agent.prompt_template)
    ])
    
    chain = prompt | model | output_parser
    response = chain.invoke({"question": input})
    logger.info(f"Response: {response}")
    return response

def invoke_with_RAG(agent: Agent, input):
    if agent.silo is None:
        print('AGENT ' + agent.name + ' has no silo to relay on.')
        return invoke(agent, input)
    
    print('AGENT ' + agent.name)

    embed = get_embedding(input)
    similar_resources = pgVectorTools.search_similar_resources(agent.silo, embed, RESULTS=1)
    info = ""
    print(similar_resources)
    for result in similar_resources:
        print(result)
        #info += "\n\nINFO CHUNK: " + result[0].page_content  + "\nSource: " + result[0].metadata["source"] + " page:" + str(result[0].metadata["page"]) + "\n\n"
        info += "\n\nINFO CHUNK: " + result.page_content
    
    if agent.output_parser_id is None:
        print("output_parser_id is None")
        output_parser = StrOutputParser()
        format_instructions = ""
    else:
        print("output_parser_id is not None")
        output_parser = get_output_parser(agent)
        format_instructions = output_parser.get_format_instructions()
        format_instructions = format_instructions.replace('{', '{{').replace('}', '}}')
    
    prompt = ChatPromptTemplate.from_messages([
            ("system", agent.system_prompt),
            ("system", "<output_format_instructions>" + format_instructions + "</output_format_instructions>"),    
            ("human", "Here is some information that might help you: " + info if info != "" else ""),    
            ("human", agent.prompt_template),
        ])
    

    model = getLLM(agent)
    chain = prompt | model | output_parser

    return chain.invoke({"question": input})


def invoke_ConversationalRetrievalChain(agent, input, session):
    print("app_id 1: ", session['app_id'])
    MEM_KEY = "MEM_KEY-" + str(agent.agent_id)
    if MEM_KEY not in session:
        print("Create memories")
        session[MEM_KEY] = ConversationBufferMemory(memory_key='chat_history', return_messages=True, output_key='answer')
    print("MEMORIES: ", session[MEM_KEY])
    print("app_id 2: ", session['app_id'])
    
    llm = getLLM(agent)

    retriever = None 
    if agent.silo:
        retriever = pgVectorTools.get_pgvector_retriever("silo_" + str(agent.silo.silo_id), agent.silo.embedding_service)
    if agent.silo is None:
        retriever = VoidRetriever()
    template = """
    Responde a las preguntas basadas en el contexto o historial de chat dado.
        <<HISTORIAL>>
        {chat_history}

        <<CONTEXTO>>
        Context: {context}

        Nueva pregunta: {question}
        """

    prompt = PromptTemplate(
        input_variables=["context", "chat_history", "question"], template=template
    )

    # Create the custom chain
    chain = ConversationalRetrievalChain.from_llm(
            llm=llm, retriever=retriever, memory=session[MEM_KEY],
            return_source_documents=False,
            verbose=True,
            combine_docs_chain_kwargs={'prompt': prompt})

    result = chain.invoke(input)
    print("RESULT: ", result)
    
    return result["answer"]

def getLLM(agent, is_vision=False):
    """
    Función base para obtener cualquier modelo LLM
    Args:
        model_info: Información del modelo
        is_vision: Boolean que indica si es un modelo de visión
    """
    if is_vision:
        ai_service = agent.vision_service_rel
    else:
        ai_service = agent.ai_service
        
    if ai_service is None:
        return None
    if ai_service.provider == ProviderEnum.OpenAI.value:
        return ChatOpenAI(model=ai_service.name, temperature=0, api_key=ai_service.api_key)
    if ai_service.provider == ProviderEnum.Anthropic.value:
        return ChatAnthropic(model=ai_service.name, temperature=0, api_key=ai_service.api_key)
    if ai_service.provider == ProviderEnum.MistralAI.value:
        if is_vision:
            mistral_client = Mistral(api_key=ai_service.api_key)
            return MistralWrapper(client=mistral_client, model_name=ai_service.name)
        return ChatMistralAI(model=ai_service.name, temperature=0, api_key=ai_service.api_key)
    if ai_service.provider.value == ProviderEnum.Custom.value:
        service = ChatOllama(
            model=ai_service.name, 
            temperature=0,
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

