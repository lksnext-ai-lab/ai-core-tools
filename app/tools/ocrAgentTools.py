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
load_dotenv()

IMAGES_PATH = os.getenv("IMAGES_PATH")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

TEXT_MODEL_TEMPLATE = """
    Eres un asistente experto en el sector financiero y analizando los datos que recibes.
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
    if not os.path.exists(output_folder):
        os.makedirs(output_folder)
    
    images = convert_from_path(pdf_path)
    image_paths = []
    
    for i, image in enumerate(images):
        image_path = os.path.join(output_folder, f"pagina_{i+1}_{pdf_path.split('/')[-1].split('.')[0]}.jpeg")
        image.save(image_path, "JPEG")
        image_paths.append(image_path)
        logging.info(f"Imagen guardada en: {image_path}")
    
    return image_paths

def convert_image_to_base64(image_path: str) -> str:
    """Convierte una imagen a formato base64"""
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')

def extract_text_from_image(base64_image: str, vision_system_prompt, pydantic_class, vision_model) -> str:
    """Extrae texto de una imagen usando el modelo de visión"""
    output_parser = JsonOutputParser(pydantic_object=pydantic_class)
    
    # Obtener el schema para las instrucciones de formato
    format_instructions = output_parser.get_format_instructions()
    
    # Crear el prompt con el schema
    chat_template = ChatPromptTemplate.from_messages([
        SystemMessage(content=vision_system_prompt),
        SystemMessage(content=f"Extrae la siguiente información de la imagen según este formato:\n{format_instructions}"),
        SystemMessage(content="Cada uno de los datos extraidos debe tener el siguiente formato: <nombre_dato>: <valor_dato>"),
        HumanMessage(content=[
            {"type": "text", "text": "Analiza la siguiente imagen y extrae cada uno de los datos que aparecen en dicha imagen."}, 
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}
        ])
    ])
    
    chain = chat_template | vision_model
    response = chain.invoke({})
    return response.content

def prepare_text_model_prompt(pdf_text: str = None, text_system_prompt: str = None, pydantic_class: Type[BaseModel] = None) -> PromptTemplate:
    """Prepara el prompt para el modelo de texto basado en los datos disponibles"""
    output_parser = JsonOutputParser(pydantic_object=pydantic_class)
    format_instructions = output_parser.get_format_instructions()
    
    TEXT_MODEL_TEMPLATE = text_system_prompt + """
    
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
            "format_instructions": format_instructions
        }
    ), output_parser

def get_data_from_extracted_text(extracted_text: str, text_model, pydantic_class, text_system_prompt: str, pdf_text: str = None) -> str:
    """Formatea los datos extraidos de la imagen y/o texto del PDF mediante el modelo de texto."""
    prompt, output_parser = prepare_text_model_prompt(pdf_text, text_system_prompt, pydantic_class)
    chain = prompt | text_model | output_parser
    response = chain.invoke({"datos_extraidos": extracted_text})
    return response
