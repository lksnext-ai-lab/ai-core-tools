import base64
import json
import logging
import os
from typing import Type
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
from langchain.prompts import PromptTemplate, ChatPromptTemplate
from pdf2image import convert_from_path
from langchain_core.output_parsers import JsonOutputParser
from pydantic import BaseModel
from pypdf import PdfReader
from mistralai import Mistral
from langchain_anthropic import ChatAnthropic
from langchain_ollama import ChatOllama
load_dotenv()

INFORMATION_EXTRACTION_SYSTEM_PROMPT = "Extract all information from this image and return it ONLY as a JSON object."
IMAGES_PATH = os.getenv("IMAGES_PATH")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")


def cargar_pdf(ruta_archivo):
    lector = PdfReader(ruta_archivo)
    texto = ""
    for pagina in lector.pages:
        texto += pagina.extract_text()
    return texto

def convert_pdf_to_images(pdf_path: str, output_folder: str) -> list[str]:
    """Convierte un PDF a imágenes y las guarda en la carpeta especificada"""
    try:
        if not os.path.exists(output_folder):
            os.makedirs(output_folder)
            logging.info("Carpeta creada")
        
        logging.info("Convirtiendo PDF")
        images = convert_from_path(
            pdf_path,
            dpi=200,
            output_folder=output_folder,
            fmt='jpeg',
            paths_only=True  
        )
        
        if not images:
            logging.error("No se generaron imágenes del PDF")
            return []
        
        logging.info(f"Imágenes generadas: {len(images)}")
        
        return images
        
    except Exception as e:
        logging.error(f"Error en la conversión del PDF a imágenes: {str(e)}")
        return []

def convert_image_to_base64(image_path: str) -> str:
    """Convierte una imagen a formato base64"""
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')

def extract_text_from_image(base64_image: str, vision_system_prompt, vision_model, document_title: str) -> str:
    """Extrae texto de una imagen usando el modelo de visión"""
    
    if isinstance(vision_model, (ChatOpenAI, ChatAnthropic)):
        chat_template = ChatPromptTemplate.from_messages([
            SystemMessage(content=vision_system_prompt),
            SystemMessage(content=f"You are an expert in analyzing documents and performing OCR on images. Your task is to extract all possible information from the provided document image. You are analyzing the document: {document_title}"),
            SystemMessage(content="You MUST extract all text and data from the image and return it as a JSON object. Do not include any explanations or additional text outside the JSON object."),
            HumanMessage(content=[
                {"type": "text", "text": INFORMATION_EXTRACTION_SYSTEM_PROMPT}, 
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}
            ])
        ])
        chain = chat_template | vision_model
        response = chain.invoke({})
        return response.content
        
    elif isinstance(vision_model, ChatOllama):
        chat_template = ChatPromptTemplate.from_messages([
            SystemMessage(content=vision_system_prompt),
            SystemMessage(content=f"You are an expert in analyzing documents and performing OCR on images. Your task is to extract all possible information from the provided document image. You are analyzing the document: {document_title}"),
            SystemMessage(content="You MUST extract all text and data from the image and return it as a JSON object. Do not include any explanations or additional text outside the JSON object."),
            HumanMessage(content=[
                {"type": "text", "text": INFORMATION_EXTRACTION_SYSTEM_PROMPT}, 
                {"type": "image_url", "image_url": f"data:image/jpeg;base64,{base64_image}"}
            ])
        ])
        chain = chat_template | vision_model
        response = chain.invoke({})
        return response.content
    
    elif isinstance(vision_model.client, Mistral):
        messages = [
            {
                "role": "system",
                "content": [
                    {
                        "type": "text", 
                        "text": f"""{vision_system_prompt}
                        You are an expert in analyzing documents and performing OCR on images. Your task is to extract all possible information from the provided document image. You are analyzing the document: {document_title}                        """
                    },
                    {
                        "type": "text",
                        "text": """You MUST extract all text and data from the image and return it as a JSON object. Do not include any explanations or additional text outside the JSON object."""
                    }
                ]
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": INFORMATION_EXTRACTION_SYSTEM_PROMPT
                    },
                    {
                        "type": "image_url",
                        "image_url": f"data:image/jpeg;base64,{base64_image}"
                    }
                ]
            }
        ]
        
        response = vision_model.client.chat.complete(
            messages=messages,
            model=vision_model.model_name
        )
        return response.choices[0].message.content
    
    else:
        raise ValueError("Modelo de visión no soportado")

def prepare_text_model_prompt(pdf_text: str = None, text_system_prompt: str = None, pydantic_class: Type[BaseModel] = None, document_title: str = None) -> PromptTemplate:
    """Prepara el prompt para el modelo de texto basado en los datos disponibles"""
    output_parser = JsonOutputParser(pydantic_object=pydantic_class)
    format_instructions = output_parser.get_format_instructions()
    
    TEXT_MODEL_TEMPLATE = text_system_prompt + """
    You are analyzing the document: {document_title}
    
    {context}
    
    IMPORTANT: You must ONLY return a valid JSON object following this exact format:
    <extracted_data>
        {datos_extraidos}
    </extracted_data>
    
    {additional_instructions}
    
    <format_instructions>
        {format_instructions}
    </format_instructions>
    """

    if pdf_text:
        context = """You have two sources of information:
        1. Text extracted directly from the PDF
        2. Text extracted through image analysis
        
        Compare both sources and use the most accurate and complete information."""
        
        additional_instructions = f"""If you find discrepancies between the sources,
        prioritize the plain text information from the PDF as it tends to be more accurate.
        
        <pdf_plain_text>
            {pdf_text}
        </pdf_plain_text>
        """

    else:
        context = "Analyze the data extracted from the image of the document."
        additional_instructions = " If you don't find any data or you aren't able to access the document. Return the same JSON object that you received as input."

    return PromptTemplate(
        template=TEXT_MODEL_TEMPLATE,
        input_variables=["datos_extraidos"],
        partial_variables={
            "context": context,
            "additional_instructions": additional_instructions,
            "format_instructions": format_instructions,
            "document_title": document_title
        }
    ), output_parser

def extract_json(response):
    logging.info(f"Respuesta recibida del modelo: {response.content}")
    json_start = response.content.index("{")
    json_end = response.content.rfind("}")
    logging.info(f"JSON extraído: {response.content[json_start:json_end + 1]}")
    return json.loads(response.content[json_start:json_end + 1])

def get_data_from_extracted_text(extracted_text: str, text_model, pydantic_class, text_system_prompt: str, pdf_text: str = None, document_title: str = None) -> str:
    """Formatea los datos extraidos de la imagen y/o texto del PDF mediante el modelo de texto."""
    logging.info("Iniciando procesamiento de texto extraído")
    prompt, output_parser = prepare_text_model_prompt(pdf_text, text_system_prompt, pydantic_class, document_title=document_title)
    
    if isinstance(text_model, ChatAnthropic):
        logging.info("Usando extract_json para modelo Claude")
        response = prompt | text_model
        result = response.invoke({"datos_extraidos": extracted_text})
        return extract_json(result)
    else:
        logging.info("Usando output parser estándar")
        chain = prompt | text_model | output_parser
        return chain.invoke({"datos_extraidos": extracted_text})

def get_document_data_from_pages(text_system_prompt: str, pages_data: list[dict], pydantic_class: Type[BaseModel], text_model, pdf_text: str = None, document_title: str = None) -> dict:
    """Obtiene los datos del documento a partir de los datos extraidos de cada una de las páginas
    
    Args:
        pages_data (list[dict]): Lista de diccionarios con los datos extraídos por página
        pydantic_class (Type[BaseModel]): Clase Pydantic para validar el formato de salida
        text_model: Modelo de lenguaje para procesar el texto
        pdf_text (str, optional): Texto plano extraído del PDF. Defaults to None.
    
    Returns:
        dict: Datos consolidados del documento
    """
    output_parser = JsonOutputParser(pydantic_object=pydantic_class)
    format_instructions = output_parser.get_format_instructions()
    
    pages_data_str = "\n".join([
        f"Page {page['page']}:\n{page['data']}" 
        for page in pages_data
    ])

    logging.info(f"Datos extraidos de las páginas: {pages_data_str}")
    if pdf_text:
        context = """IMPORTANT: You must ONLY return a valid JSON object that matches the format specified in the format instructions.
        DO NOT include any explanations or additional text.
        
        You have two sources of information:
        1. Text extracted directly from the PDF (more reliable source)
        2. Data extracted from each page of the document
        
        Rules for data consolidation:
        - Prioritize information based on:
            * Pages with more complete data sets
            * Initial pages of the document (pages 1-2 have higher priority)
        - Discard null values when a field has values on other pages
        - For conflicting values between pages:
            * Compare with PDF text for validation
            * Select the most complete and accurate value
        - For list fields:
            * Combine unique elements
            * Remove duplicates keeping most detailed descriptions
            * Validate against PDF text
        
        <pdf_plain_text>
        {pdf_text}
        </pdf_plain_text>
        """
    else:
        context = """IMPORTANT: You must ONLY return a valid JSON object that matches the format specified in the format instructions.
        DO NOT include any explanations or additional text.
        
        Rules for data consolidation:
        - Prioritize information based on:
            * Pages with more complete data sets
            * Initial pages of the document (pages 1-2 have higher priority)
        - Discard null values when a field has values on other pages
        - For conflicting values between pages:
            * Select the most complete and accurate value
            * Note discrepancies if accuracy cannot be determined
        - For list fields:
            * Combine unique elements
            * Remove duplicates keeping most detailed descriptions
        """

    system_prompt = text_system_prompt + """
    Document being analyzed: {document_title}
    
    {context}

    Data extracted by page:
    <data_extracted_by_page>
        {pages_data}
    </data_extracted_by_page>

    <format_instructions>
        {format_instructions}
    </format_instructions>

    CRITICAL REQUIREMENTS:
    1. Return ONLY a JSON object
    2. The JSON MUST follow the exact format specified above
    3. DO NOT include any text before or after the JSON
    4. DO NOT include any explanations or analysis
    """

    prompt = PromptTemplate(
        template=system_prompt,
        input_variables=["pages_data"],
        partial_variables={
            "context": context,
            "format_instructions": format_instructions,
            "document_title": document_title
        }
    )

    if isinstance(text_model, (ChatAnthropic, ChatOllama)):
        logging.info("Usando extract_json para modelo Claude")
        response = prompt | text_model
        result = response.invoke({"pages_data": pages_data_str})
        return extract_json(result)
    else:
        logging.info("Usando output parser estándar")
        chain = prompt | text_model | output_parser
        return chain.invoke({"pages_data": pages_data_str})

def format_data_with_text_llm(vision_output: list, text_model, pydantic_class, text_system_prompt: str, pdf_text: str, document_title: str) -> list:
    """Formatea los datos cuando hay texto plano disponible usando el LLM"""
    formatted_data_by_page = []
    for output in vision_output:
        logging.info("Formateando datos para imagen.")
        formatted_text = get_data_from_extracted_text(
            output["extracted_text"], 
            text_model, 
            pydantic_class, 
            text_system_prompt, 
            pdf_text, 
            document_title
        )
        formatted_data_by_page.append({
            "page": len(formatted_data_by_page) + 1,
            "data": formatted_text
        })
    return formatted_data_by_page


def format_data_from_vision(vision_output: list) -> list:
    """Formatea los datos directamente del output de visión cuando no hay texto plano"""
    formatted_data_by_page = []
    for output in vision_output:
        try:
            if isinstance(output["extracted_text"], dict):
                json_data = output["extracted_text"]
            else:
                try:
                    json_data = json.loads(output["extracted_text"])
                except json.JSONDecodeError:
                    text = output["extracted_text"]
                    json_start = text.find("{")
                    json_end = text.rfind("}") + 1
                    if json_start == -1 or json_end == 0:
                        logging.error("No se encontró un objeto JSON válido en el texto")
                        continue
                    json_str = text[json_start:json_end]
                    json_data = json.loads(json_str)
            
            formatted_data_by_page.append({
                "page": len(formatted_data_by_page) + 1,
                "data": json_data
            })
        except Exception as e:
            logging.error(f"Error al parsear JSON de vision_output: {e}")
            continue
    return formatted_data_by_page





