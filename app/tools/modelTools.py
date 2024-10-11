from flask import session
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_anthropic import ChatAnthropic
from langchain_core.prompts import ChatPromptTemplate, SystemMessagePromptTemplate
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnablePassthrough
from langchain.prompts.prompt import PromptTemplate
from langchain.chains.llm import LLMChain
from langchain.chains.combine_documents import create_stuff_documents_chain
from langchain.chains.conversational_retrieval.base import ConversationalRetrievalChain
from langchain.memory import ConversationBufferMemory

from app.model.agent import Agent
from app.extensions import db
from app.tools.pgVectorTools import PGVectorTools

pgVectorTools = PGVectorTools(db)



def get_embedding(text):
    embeddings = OpenAIEmbeddings()
    return embeddings.embed_query(text)


def invoke(agent, input):
    print('AGENT ' + agent.name)
    sys_message = SystemMessage(agent.system_prompt)
    user_message = HumanMessage(agent.prompt_template)

    prompt = ChatPromptTemplate.from_messages([
            ("system", agent.system_prompt),    
            ("human", agent.prompt_template),
        ])
    

    output_parser = StrOutputParser()
    model = getLLM(agent)
    chain = (
        {"question": RunnablePassthrough()} 
        | prompt
        | model
        | output_parser
    )

    return chain.invoke(input)

def invoke_rag_with_repo(agent: Agent, input):
    if agent.repository is None:
        print('AGENT ' + agent.name + ' has no repository to relay on.')
        return invoke(agent, input)
    
    print('AGENT ' + agent.name)

    embed = get_embedding(input)
    similar_resources = pgVectorTools.search_similar_resources(agent.repository_id, embed, RESULTS=1)
    info = ""
    print(similar_resources)
    for result in similar_resources:
        print(result)
        #info += "\n\nINFO CHUNK: " + result[0].page_content  + "\nSource: " + result[0].metadata["source"] + " page:" + str(result[0].metadata["page"]) + "\n\n"
        info += "\n\nINFO CHUNK: " + result.page_content
    
    prompt = ChatPromptTemplate.from_messages([
            ("system", agent.system_prompt),
            ("human", "Here is some information that might help you: " + info if info != "" else ""),    
            ("human", agent.prompt_template),
        ])
    

    output_parser = StrOutputParser()
    model = getLLM(agent)
    chain = (
        {"question": RunnablePassthrough()} 
        | prompt
        | model
        | output_parser
    )

    return chain.invoke(input)


def invoke_ConversationalRetrievalChain(agent, input, session):
    print("app_id 1: ", session['app_id'])
    MEM_KEY = "MEM_KEY-" + str(agent.agent_id)
    if MEM_KEY not in session:
        print("Create memories")
        session[MEM_KEY] = ConversationBufferMemory(memory_key='chat_history', return_messages=True, output_key='answer')
    print("MEMORIES: ", session[MEM_KEY])
    print("app_id 2: ", session['app_id'])
    
    llm = getLLM(agent)

    retriever = pgVectorTools.get_pgvector_retriever(agent.repository_id)
   
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
        return ChatOpenAI(model=agent.model.name)
    if agent.model.provider == "Anthropic":
        return ChatAnthropic(model=agent.model.name)
    return None
