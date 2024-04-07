from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_core.prompts import ChatPromptTemplate, SystemMessagePromptTemplate
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnablePassthrough 
from model.agent import Agent
import tools.milvusTools as milvusTools


from langchain.prompts.prompt import PromptTemplate



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
    model = ChatOpenAI(model=agent.model.name)
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
    similar_resources = milvusTools.search_similar_resources(agent.repository_id, embed, RESULTS=1)
    info = ""
    for result in similar_resources:
        #print(result)
        #info += "\n\nINFO CHUNK: " + result[0].page_content  + "\nSource: " + result[0].metadata["source"] + " page:" + str(result[0].metadata["page"]) + "\n\n"
        info += "\n\nINFO CHUNK: " + result[0].page_content
    
    prompt = ChatPromptTemplate.from_messages([
            ("system", agent.system_prompt),
            ("human", "Here is some information that might help you: " + info if info != "" else ""),    
            ("human", agent.prompt_template),
        ])
    

    output_parser = StrOutputParser()
    model = ChatOpenAI(model=agent.model.name)
    chain = (
        {"question": RunnablePassthrough()} 
        | prompt
        | model
        | output_parser
    )

    return chain.invoke(input)
