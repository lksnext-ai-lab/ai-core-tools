import os
from dotenv import load_dotenv
from flask import session
from typing import Dict, Type, Union
from pydantic import BaseModel, Field
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_anthropic import ChatAnthropic
from langchain_core.prompts import ChatPromptTemplate, SystemMessagePromptTemplate
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.output_parsers import StrOutputParser, JsonOutputParser
from langchain_core.retrievers import BaseRetriever

from langchain_core.runnables import RunnablePassthrough
from langchain.prompts.prompt import PromptTemplate
from langchain.chains.llm import LLMChain
from langchain.chains.combine_documents import create_stuff_documents_chain
from langchain.chains.conversational_retrieval.base import ConversationalRetrievalChain
from langchain.memory import ConversationBufferMemory
from langchain_mistralai import ChatMistralAI

from app.model.output_parser import OutputParser
from app.model.agent import Agent
from app.extensions import db
from app.tools.pgVectorTools import PGVectorTools
from app.tools.outputParserTools import create_dynamic_pydantic_model, get_parser_model_by_id
from typing import List
from langchain_core.documents import Document

load_dotenv()

pgVectorTools = PGVectorTools(db)

def get_embedding(text):
    embeddings = OpenAIEmbeddings()
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
    return chain.invoke({"question": input})

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
        retriever = pgVectorTools.get_pgvector_retriever("silo_" + str(agent.silo.silo_id))
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

def getLLM(agent):
    if agent.model is None:
        return None
    if agent.model.provider == "OpenAI":
        return ChatOpenAI(model=agent.model.name, api_key=os.getenv('OPENAI_API_KEY'))
    if agent.model.provider == "Anthropic":
        return ChatAnthropic(model=agent.model.name, api_key=os.getenv('ANTHROPIC_API_KEY'))
    if agent.model.provider == "MistralAI":
        return ChatMistralAI(model=agent.model.name, api_key=os.getenv('MISTRAL_API_KEY'))
    return None



class VoidRetriever(BaseRetriever):
    
    def _get_relevant_documents(self, query: str) -> List[Document]:
        return []

    async def _aget_relevant_documents(self, query: str) -> List[Document]:
        return []