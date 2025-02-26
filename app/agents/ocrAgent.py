import os
from typing import List, Dict, Any, Annotated, Literal, Type
from langchain_openai import ChatOpenAI
from pydantic import BaseModel
from typing_extensions import TypedDict
from dotenv import load_dotenv
import logging
from langsmith import Client

from app.extensions import db

from langchain_core.messages import BaseMessage, HumanMessage, AIMessage

from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages

from app.tools.aiServiceTools import MistralWrapper, getLLM
from langchain_mistralai import ChatMistralAI

from app.tools.outputParserTools import create_model_from_json_schema
from app.model.ocr_agent import OCRAgent
from app.tools.ocrAgentTools import (
    convert_pdf_to_images, 
    convert_image_to_base64, 
    extract_text_from_image, 
    cargar_pdf, 
    get_document_data_from_pages,
    format_data_with_text_llm,
    format_data_from_vision
)

from langchain_anthropic import ChatAnthropic
from langchain_ollama.llms import OllamaLLM

load_dotenv()

client = Client()
os.environ["LANGCHAIN_TRACING_V2"] = "true"
os.environ["LANGCHAIN_PROJECT"] = "ia-core-tools"
os.environ["LANGCHAIN_ENDPOINT"] = "https://api.smith.langchain.com"

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('agent_process.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)

class State(TypedDict):
    pdf_path: str
    images: List[str]
    vision_output: List[Dict[str, Any]]
    formatted_llm_text_output: List[Dict[str, Any]]
    final_output: Dict[str, Any]
    pdf_text: str
    has_plain_text: bool
    images_path: str
    agent: OCRAgent
    vision_model: ChatOpenAI
    text_model: ChatOpenAI
    pydantic_class: Type[BaseModel]
    messages: Annotated[List[BaseMessage], add_messages]


def get_or_create_graph():
    """Crea y retorna un nuevo grafo compilado"""
    graph_builder = StateGraph(State)
    
    # Añadir nodos al grafo
    graph_builder.add_node("get_agent_llms", get_agent_llms)
    graph_builder.add_node("get_agent_output_parser", get_agent_output_parser)
    graph_builder.add_node("pdf text checker", check_pdf_contains_plain_text)
    graph_builder.add_node("pdf text extractor", extract_text_from_pdf)
    graph_builder.add_node("pdf to images converter", pdf_to_images)
    graph_builder.add_node("vision data extractor", extract_data_from_images)
    graph_builder.add_node("data analyzer and formatter llm", get_and_format_data_with_llm)
    graph_builder.add_node("document data integration by pages", get_final_output)

    # Conexiones
    graph_builder.add_edge(START, "get_agent_llms")
    graph_builder.add_edge("get_agent_llms", "get_agent_output_parser")
    graph_builder.add_edge("get_agent_output_parser", "pdf text checker")
    
    # Conexiones para el flujo con visión
    graph_builder.add_conditional_edges(
        source="pdf text checker",
        path=determine_path_with_vision
    )
    graph_builder.add_edge("pdf text extractor", "pdf to images converter")
    graph_builder.add_edge("pdf to images converter", "vision data extractor")
    graph_builder.add_edge("vision data extractor", "data analyzer and formatter llm")
    graph_builder.add_edge("data analyzer and formatter llm", "document data integration by pages")
    graph_builder.add_edge("document data integration by pages", END)
    
    return graph_builder.compile()

def get_agent_llms(state: State):
    """Obtiene los modelos específicos para el agente OCR"""
    vision_model = getLLM(state["agent"].vision_service_rel, is_vision=True)
    text_model = getLLM(state["agent"].ai_service)
    
    if vision_model is None or text_model is None:
        raise ValueError("No se pudieron inicializar los modelos necesarios")
        
    return {"vision_model": vision_model, "text_model": text_model}

def get_agent_output_parser(state: State):
    """Obtiene y construye el modelo Pydantic para el parser de salida del agente"""
    output_parser = None
    if state["agent"].output_parser:
        try:
            schema_data = state["agent"].output_parser.fields
            output_parser = create_model_from_json_schema(
                schema_data,
                state['agent'].output_parser.name
            )
            logging.info(f"Parser creado exitosamente para {state['agent'].output_parser.name}")
        except Exception as e:
            logging.error(f"Error al crear el parser: {str(e)}")
            output_parser = None
            
    return {"pydantic_class": output_parser}

def check_pdf_contains_plain_text(state: State):
    """Verifica si el PDF contiene texto plano o es una imagen escaneada"""
    logging.info(f"Verificando si el PDF '{state['pdf_path']}' contiene texto plano...")
    try:
        logging.info("Iniciando verificación de texto en PDF...")
        pdf_text = cargar_pdf(state["pdf_path"])
        
        if not pdf_text or len(pdf_text.strip()) < 50:
            state["has_plain_text"] = False
            logging.info(f"Resultado de verificación: contiene texto plano = {state['has_plain_text']}")
            return {
                "has_plain_text": False,
                "messages": [AIMessage(content="El PDF no contiene texto plano.")]
            }
            
        caracteres_validos = sum(1 for c in pdf_text if c.isprintable() and not c.isspace())
        ratio_caracteres = caracteres_validos / len(pdf_text)
        
        state["has_plain_text"] = ratio_caracteres > 0.3
        logging.info(f"Resultado de verificación: contiene texto plano = {state['has_plain_text']}")
        return {
            "has_plain_text": state["has_plain_text"],
            "messages": [AIMessage(content=f"Verificación completada. El PDF {'contiene' if state['has_plain_text'] else 'no contiene'} texto plano.")]
        }
        
    except Exception as e:
        logging.error(f"Error al verificar el texto del PDF: {e}")
        return {
            "has_plain_text": False,
            "messages": [AIMessage(content=f"Error al verificar el PDF: {str(e)}")]
        }

def pdf_to_images(state: State):
    """Convierte el PDF a imágenes"""
    logging.info("Iniciando conversión de PDF a imágenes...")
    try:
        images = convert_pdf_to_images(
            pdf_path=state["pdf_path"],
            output_folder=state["images_path"]
        )
        logging.info(f"PDF convertido exitosamente. {len(images)} imágenes generadas")
        return {
            "images": images,
            "messages": [AIMessage(content=f"PDF convertido a {len(images)} imágenes.")]
        }
    except Exception as e:
        return {
            "images": [],
            "messages": [AIMessage(content=f"Error al convertir PDF a imágenes: {str(e)}")]
        }

def extract_text_from_pdf(state: State):
    """Extrae el texto plano del PDF si es posible"""
    logging.info("Iniciando extracción de texto del PDF...")
    try:
        pdf_text = cargar_pdf(state["pdf_path"])
        logging.info(f"Texto extraído exitosamente. Longitud: {len(pdf_text)} caracteres")
        return {
            "pdf_text": pdf_text,
            "messages": [AIMessage(content="Texto extraído exitosamente del PDF.")]
        }
    except Exception as e:
        logging.error(f"Error al extraer texto del PDF: {e}")
        return {
            "pdf_text": "",
            "messages": [AIMessage(content=f"Error al extraer texto: {str(e)}")]
        }

def extract_data_from_images(state: State):
    """Extrae datos de las imágenes usando el modelo de visión"""
    logging.info("Iniciando extracción de datos de las imágenes...")
    vision_output = []
    try:
        for image_path in state["images"]:
            logging.info(f"Procesando imagen: {image_path}")
            base64_image = convert_image_to_base64(image_path)
            extracted_text = extract_text_from_image(base64_image, state["agent"].vision_system_prompt, state["pydantic_class"], state["vision_model"], state["pdf_path"].split("/")[-1])
            logging.info(f"Texto extraído de la imagen: {extracted_text}")
            vision_output.append({
                "image_path": image_path,
                "extracted_text": extracted_text
            })
        logging.info(f"Procesamiento de imágenes completado. {len(vision_output)} imágenes procesadas")
        return {
            "vision_output": vision_output,
            "messages": [AIMessage(content=f"Procesadas {len(vision_output)} imágenes con éxito.")]
        }
    except Exception as e:
        return {
            "vision_output": [],
            "messages": [AIMessage(content=f"Error al procesar imágenes: {str(e)}")]
        }

def get_and_format_data_with_llm(state: State):
    """Formatea los datos extraídos usando el LLM"""
    logging.info("Iniciando formateo de datos con LLM...")
    try:
        if state["has_plain_text"]:
            formatted_data_by_page = format_data_with_text_llm(
                state["vision_output"],
                state["text_model"],
                state["pydantic_class"],
                state["agent"].text_system_prompt,
                state["pdf_text"],
                state["pdf_path"].split("/")[-1]
            )
        else:
            formatted_data_by_page = format_data_from_vision(state["vision_output"])
        
        logging.info("Formateo de datos completado")
        logging.info(f"Datos formateados: {formatted_data_by_page}")
        return {
            "formatted_llm_text_output": formatted_data_by_page,
            "messages": [AIMessage(content="Datos formateados exitosamente.")]
        }
    except Exception as e:
        logging.error(f"Error en get_and_format_data_with_llm: {str(e)}")
        return {
            "formatted_llm_text_output": [],
            "messages": [AIMessage(content=f"Error al formatear datos: {str(e)}")]
        }

def get_final_output(state: State):
    """Obtiene los datos del documento a partir de los datos extraidos de cada una de las páginas"""
    logging.info("Iniciando obtención de datos del documento a partir de los datos extraidos de cada una de las páginas...")
    text_system_prompt = state["agent"].text_system_prompt
    try:
        if state["has_plain_text"]:
            document_data = get_document_data_from_pages(text_system_prompt, state["formatted_llm_text_output"], state["pydantic_class"], state["text_model"], state["pdf_text"], state["pdf_path"].split("/")[-1])
        else:
            document_data = get_document_data_from_pages(text_system_prompt, state["formatted_llm_text_output"], state["pydantic_class"], state["text_model"], document_title= state["pdf_path"].split("/")[-1])
        logging.info(f"Datos del documento extraidos exitosamente: {document_data}")
        return {
            "final_output": document_data,
            "messages": [AIMessage(content="Datos del documento extraidos exitosamente.")]
        }
    except Exception as e:
        logging.error(f"Error al obtener los datos del documento: {e}")
        return {
            "final_output": {},
            "messages": [AIMessage(content=f"Error al obtener los datos del documento: {str(e)}")]
        }

def determine_path_with_vision(state: State) -> Literal["pdf text extractor", "pdf to images converter"]:
    """Determina el siguiente nodo basado en el resultado del PDF checker"""
    has_text = state.get("has_plain_text", False)
    return "pdf text extractor" if has_text else "pdf to images converter"

def process_pdf(agent_id: int, pdf_path: str, images_path: str):
    try:
        agent = db.session.query(OCRAgent).filter(OCRAgent.agent_id == agent_id).first()
        if not agent:
            raise ValueError(f"No se encontró el agente con ID {agent_id}")
        
        graph = get_or_create_graph()
        
        extracted_data = graph.invoke({
            "pdf_path": pdf_path,
            "images_path": images_path,
            "images": [],
            "vision_output": [],
            "formatted_llm_text_output": {},
            "final_output": {},
            "pdf_text": "",
            "has_plain_text": False,
            "messages": [
                HumanMessage(content="Inicio del procesamiento del PDF")
            ],
            "agent": agent,
            "vision_model": None,
            "text_model": None,
            "pydantic_class": None,
        })["final_output"]

        try:
            if os.path.exists(pdf_path):
                os.remove(pdf_path)
                logging.info(f"PDF eliminado: {pdf_path}")

            if os.path.exists(images_path):
                for file in os.listdir(images_path):
                    file_path = os.path.join(images_path, file)
                    if os.path.isfile(file_path):
                        os.remove(file_path)
                        logging.info(f"Imagen eliminada: {file_path}")
                os.rmdir(images_path)
                logging.info(f"Directorio de imágenes eliminado: {images_path}")
        except Exception as cleanup_error:
            logging.error(f"Error al limpiar archivos: {cleanup_error}")

        return extracted_data

    except Exception as e:
        try:
            if os.path.exists(pdf_path):
                os.remove(pdf_path)
            if os.path.exists(images_path):
                for file in os.listdir(images_path):
                    os.remove(os.path.join(images_path, file))
                os.rmdir(images_path)
        except:
            pass
        raise e