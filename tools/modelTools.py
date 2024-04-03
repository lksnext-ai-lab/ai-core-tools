from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate, SystemMessagePromptTemplate
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnablePassthrough
from model.agent import Agent


from langchain.prompts.prompt import PromptTemplate



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


