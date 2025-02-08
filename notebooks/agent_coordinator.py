from typing import Dict, Any
from langchain.agents import AgentExecutor, create_openai_functions_agent
from langchain_core.tools import Tool
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
import requests
import json

class CompanyInfoTool:
    def __init__(self):
        self.base_url = "http://127.0.0.1:5000/api/app/2/call/5"
        self.api_key = "KLLKxCPkOAmPcLHKl40FUcUohEl0UjFoYbT48FNIKRjw28E0"
        
    def __call__(self, question: str) -> str:
        headers = {
            'accept': '*/*',
            'Content-Type': 'application/json',
            'x-api-key': self.api_key
        }
        data = {
            'question': question
        }
        response = requests.post(self.base_url, headers=headers, json=data)
        return response.json()

class EmailWriterTool:
    def __init__(self):
        self.base_url = "http://127.0.0.1:5000/api/app/2/call/6"
        self.api_key = "KLLKxCPkOAmPcLHKl40FUcUohEl0UjFoYbT48FNIKRjw28E0"
        
    def __call__(self, context: str) -> str:
        headers = {
            'accept': '*/*',
            'Content-Type': 'application/json',
            'x-api-key': self.api_key
        }
        data = {
            'question': context
        }
        response = requests.post(self.base_url, headers=headers, json=data)
        return response.json()

def create_email_agent():
    # Crear las herramientas
    company_info = CompanyInfoTool()
    email_writer = EmailWriterTool()

    # Definir las herramientas para el agente
    tools = [
        Tool(
            name="consultar_informacion",
            func=company_info,
            description="Usa esta herramienta para obtener información sobre la empresa, departamentos y empleados. Input: una pregunta sobre la empresa"
        ),
        Tool(
            name="escribir_email",
            func=email_writer,
            description="Usa esta herramienta para generar un correo electrónico. Input: contexto y detalles para el correo"
        )
    ]

    # Definir el prompt para el agente
    prompt = ChatPromptTemplate.from_messages([
        ("system", """Eres un asistente experto en generar correos electrónicos corporativos.
        Tienes acceso a dos herramientas:
        1. consultar_informacion: para obtener datos sobre la empresa, departamentos y empleados
        2. escribir_email: para generar el correo electrónico final
        
        Analiza cada solicitud cuidadosamente y decide qué información necesitas consultar antes de generar el correo.
        Asegúrate de obtener toda la información relevante antes de escribir el correo."""),
        ("user", "{input}"),
        ("assistant", "{agent_scratchpad}")
    ])

    # Crear el modelo base
    llm = ChatOpenAI(
        temperature=0,
        api_key="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"  # Reemplaza esto con tu API key de OpenAI
    )

    # Crear el agente
    agent = create_openai_functions_agent(llm, tools, prompt)
    agent_executor = AgentExecutor(agent=agent, tools=tools, verbose=True)

    return agent_executor

# Ejemplo de uso
if __name__ == "__main__":
    agent = create_email_agent()
    
    # Ejemplo de solicitud
    task = """
    Redactame un correo para el departamento de recursos humanos para avisarles de despidos masivos.
    """
    
    result = agent.invoke({"input": task})
    print("\nResultado final:")
    print(result["output"]) 