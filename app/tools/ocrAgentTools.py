import base64
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
load_dotenv()

IMAGES_PATH = os.getenv("IMAGES_PATH")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

TEXT_MODEL_TEMPLATE = """
    Eres un asistente experto analizando los datos que recibes.
    Formatea los siguientes datos extraidos de una imagen:
    <datos_extraidos>
        {datos_extraidos}
    </datos_extraidos>
    <format_instructions>
        {format_instructions}
    </format_instructions>
"""
INPUT_VARIABLES = ["datos_extraidos"]

multimodal_model = ChatOpenAI(
    openai_api_key=OPENAI_API_KEY,
    model="gpt-4o",
    temperature=0,
)

def cargar_pdf(ruta_archivo):
    lector = PdfReader(ruta_archivo)
    texto = ""
    for pagina in lector.pages:
        texto += pagina.extract_text()
    return texto

def convert_pdf_to_images(pdf_path: str, output_folder: str) -> list[str]:
    """Convierte un PDF a imágenes y las guarda en la carpeta especificada"""
    try:
        # Asegurar que las carpetas existen
        if not os.path.exists(output_folder):
            os.makedirs(output_folder)
            logging.info(f"Carpeta creada: {output_folder}")
        
        # Convertir PDF a imágenes con dpi más alto para mejor calidad
        logging.info(f"Convirtiendo PDF: {pdf_path}")
        images = convert_from_path(
            pdf_path,
            dpi=200,
            output_folder=output_folder,
            fmt='jpeg',
            paths_only=True  # Esto hará que devuelva las rutas directamente
        )
        
        if not images:
            logging.error("No se generaron imágenes del PDF")
            return []
        
        logging.info(f"Imágenes generadas: {len(images)}")
        for img_path in images:
            logging.info(f"Imagen guardada en: {img_path}")
        
        return images
        
    except Exception as e:
        logging.error(f"Error en la conversión del PDF a imágenes: {str(e)}")
        return []

def convert_image_to_base64(image_path: str) -> str:
    """Convierte una imagen a formato base64"""
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')



def extract_text_from_image(base64_image: str, vision_system_prompt, pydantic_class, vision_model, document_title: str) -> str:
    """Extrae texto de una imagen usando el modelo de visión"""
    output_parser = JsonOutputParser(pydantic_object=pydantic_class)
    format_instructions = output_parser.get_format_instructions()
    
    if isinstance(vision_model, ChatOpenAI):
        # Usar el modelo de OpenAI
        chat_template = ChatPromptTemplate.from_messages([
            SystemMessage(content=vision_system_prompt),
            SystemMessage(content=f"Estás analizando el documento: {document_title}"),
            SystemMessage(content=f"Extrae la siguiente información de la imagen según este formato:\n{format_instructions}"),
            SystemMessage(content="En caso de que no se pueda extraer el dato o no encuentres los campos que se te piden, manten el formato pero con un valor nulo en el campo que no se pudo extraer."),
            HumanMessage(content=[
                {"type": "text", "text": f"Analiza la siguiente imagen del documento '{document_title}' y extrae los datos que aparecen en dicha imagen."}, 
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}
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
                        Estás analizando el documento: {document_title}
                        """
                    },
                    {
                        "type": "text",
                        "text": f"""Extrae la siguiente información de la imagen según este formato:
                        {format_instructions}
                        En caso de que no se pueda extraer el dato o no encuentres los campos que se te piden, manten el formato pero con un valor nulo en el campo que no se pudo extraer.
                        """
                    }
                ]
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": f"Analiza la siguiente imagen del documento '{document_title}' y extrae los datos que aparecen en dicha imagen."
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
    Estás analizando el documento: {document_title}
    
    {context}
    
    Devuelve los datos necesarios en formato JSON:
    <datos_extraidos>
        {datos_extraidos}
    </datos_extraidos>
    
    {additional_instructions}
    
    <format_instructions>
        {format_instructions}
    </format_instructions>
    """

    if pdf_text:
        context = """Tienes dos fuentes de información:
        1. Texto extraído directamente del PDF
        2. Texto extraído mediante análisis de imagen
        
        Compara ambas fuentes y utiliza la información más precisa y completa."""
        
        additional_instructions = f"""Si encuentras discrepancias entre las fuentes, 
        prioriza la información del texto plano del PDF ya que suele ser más precisa.
        
        <texto_plano_pdf>
            {pdf_text}
        </texto_plano_pdf>
        """

    else:
        context = "Analiza los datos extraídos de la imagen del documento."
        additional_instructions = "Asegúrate de capturar todos los detalles relevantes de los datos extraídos."

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

def get_data_from_extracted_text(extracted_text: str, text_model, pydantic_class, text_system_prompt: str, pdf_text: str = None, document_title: str = None) -> str:
    """Formatea los datos extraidos de la imagen y/o texto del PDF mediante el modelo de texto."""
    prompt, output_parser = prepare_text_model_prompt(pdf_text, text_system_prompt, pydantic_class, document_title= document_title)
    chain = prompt | text_model | output_parser
    response = chain.invoke({"datos_extraidos": extracted_text})
    return response

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
        f"Página {page['page']}:\n{page['data']}" 
        for page in pages_data
    ])
        
    if pdf_text:
        context = """Eres un experto en análisis y consolidación de datos de documentos financieros. Tu tarea es consolidar la información extraída de múltiples páginas en un único JSON coherente.

        Tienes dos fuentes de información:
        1. Texto extraído directamente del PDF (más fiable)
        2. Datos extraídos de cada página del documento

        Reglas de consolidación:
        - Para campos con valores en algunas páginas y nulos en otras, descarta los valores nulos
        - Para campos con valores diferentes entre páginas:
            * Compara con el texto del PDF para validar la precisión
            * Selecciona la descripción más completa y precisa del campo
        - Para campos que contienen listas:
            * Combina los elementos únicos de todas las páginas
            * Verifica contra el texto del PDF para validar la completitud
            * Elimina duplicados manteniendo las descripciones más detalladas
        
        <texto_plano_pdf>
        {pdf_text}
        </texto_plano_pdf>
        """
    else:
        context = """Eres un experto en análisis y consolidación de datos de documentos financieros. Tu tarea es consolidar la información extraída de múltiples páginas en un único JSON coherente.

        Reglas de consolidación:
        - Para campos con valores en algunas páginas y nulos en otras, descarta los valores nulos
        - Para campos con valores diferentes entre páginas:
            * Selecciona la descripción más completa y precisa del campo
            * Si no hay forma de determinar cuál es más preciso, indica la discrepancia en el campo
        - Para campos que contienen listas:
            * Combina los elementos únicos de todas las páginas
            * Elimina duplicados manteniendo las descripciones más detalladas
        
        """

    system_prompt = text_system_prompt + """
    Estás analizando el documento: {document_title}
    
    {context}

    Analiza y consolida los siguientes datos extraídos por página:
    <datos_extraidos_por_pagina>
        {pages_data}
    </datos_extraidos_por_pagina>

    <format_instructions>
        {format_instructions}
    </format_instructions>

    Asegúrate de que el JSON resultante:
    1. Cumpla con el esquema especificado
    2. Contenga la información más completa y precisa disponible
    3. Mantenga la consistencia en el formato de los datos
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

    chain = prompt | text_model | output_parser
    
    response = chain.invoke({"pages_data": pages_data_str})
    return response



