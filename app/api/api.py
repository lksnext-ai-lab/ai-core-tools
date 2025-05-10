from flask import session, request, jsonify, current_app
from flask_openapi3 import APIBlueprint, Tag
from agents.ocrAgent import process_pdf
from model.agent import Agent
from extensions import db
import os
import logging
from api.api_auth import require_auth
from agents.ocrAgent import OCRAgent
from api.pydantic.agent_pydantic import AgentPath, ChatRequest, AgentResponse, OCRResponse
from tools.agentTools import create_agent, MCPClientManager
from langchain_core.messages import HumanMessage, AIMessage
from langchain.callbacks.tracers import LangChainTracer
from langsmith import Client
from services.agent_cache_service import AgentCacheService

# Logging configuration
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

api_tag = Tag(name="API", description="Main API endpoints")
security=[{"api_key":[]}]
api = APIBlueprint('api', __name__, url_prefix='/api/app/<int:app_id>',abp_security=security)

MSG_LIST = "MSG_LIST"


@api.post('/call/<int:agent_id>', 
    summary="Call agent", 
    tags=[api_tag],
    responses={"200": AgentResponse}
)
@require_auth
def call_agent(path: AgentPath, body: ChatRequest):
    """
    Punto de entrada para llamadas al agente que garantiza que la conexión permanezca
    abierta hasta que se complete la respuesta del agente.
    """
    try:
        question = body.question
        agent = db.session.query(Agent).filter(Agent.agent_id == path.agent_id).first()
        
        if agent is None:
            return {"error": "Agent not found"}, 404
        
        if agent.request_count is None:
            agent.request_count = 0
        agent.request_count += 1
        db.session.commit()
        
        tracer = None
        if agent.app.langsmith_api_key is not None and agent.app.langsmith_api_key != "":
            client = Client(api_key=agent.app.langsmith_api_key)
            tracer = LangChainTracer(client=client, project_name=agent.app.name)

        # Crear una tarea asíncrona pero ejecutarla de forma sincrónica
        result = current_app.ensure_sync(process_agent_request)(agent, question, tracer)
        
        # Manejar y formatear el resultado
        if isinstance(result, tuple) and len(result) == 2 and isinstance(result[1], int):
            # Es una respuesta de error
            return result
        
        # Es una respuesta exitosa
        if MSG_LIST not in session:
            session[MSG_LIST] = []
        session[MSG_LIST].append(result["generated_text"])
        
        return result
        
    except Exception as e:
        logger.error(f"Error in call_agent: {str(e)}", exc_info=True)
        return {"error": str(e)}, 500


async def process_agent_request(agent, question, tracer):
    """
    Procesa la solicitud del agente de forma asíncrona.
    """
    try:
        logger.info(f"Processing agent request for agent {agent.agent_id}: {question[:50]}...")
        
        # Only try to get agent from cache if it has memory enabled
        agent_x = None
        if agent.has_memory:
            agent_x = AgentCacheService.get_cached_agent(agent.agent_id)
        
        if agent_x is None:
            # Create new agent instance if not in cache or if agent has no memory
            logger.info(f"Creating new agent instance for {agent.agent_id}")
            agent_x = await create_agent(agent)
            # Only cache if agent has memory enabled
            if agent.has_memory:
                AgentCacheService.cache_agent(agent.agent_id, agent_x)
                logger.info(f"Agent {agent.agent_id} cached successfully")
            else:
                logger.info(f"Agent {agent.agent_id} not cached as it has no memory enabled")
        
        config = {
            "configurable": {
                "question": question,
                "thread_id": f"thread_{agent.agent_id}"  # Add unique thread id based on agent id
            }
        }
        
        if tracer is not None:
            config["callbacks"] = [tracer]

        # Initialize state with messages and checkpoint if memory is enabled
        initial_state = {
            "messages": [],
            "checkpoint": None if not agent.has_memory else {}
        }
        
        result = await agent_x.ainvoke(initial_state, config=config)
        logger.info(f"Agent {agent.agent_id} response: {result}")
        # Determinar la respuesta basada en si tenemos structured_response o mensajes
        response_text = ""
        if "structured_response" in result:
            response_text = result["structured_response"].model_dump()
        else:
            final_message = next((msg for msg in reversed(result['messages']) if isinstance(msg, AIMessage)), None)
            response_text = final_message.content if final_message else str(result)
        
        data = {
            "input": question,
            "generated_text": response_text,
            "control": {
                "temperature": 0.8,
                "max_tokens": 100,
                "top_p": 0.9,
                "frequency_penalty": 0.5,
                "presence_penalty": 0.5,
                "stop_sequence": "\n\n"
            },
            "metadata": {
                "model_name": agent.ai_service.name,
                "timestamp": "2024-04-04T12:00:00Z"
            }
        }
        
        return data
    
    except Exception as e:
        logger.error(f"Error processing agent request: {str(e)}", exc_info=True)
        return {"error": str(e)}, 500
    finally:
        # Close MCP client when the application shuts down
        await MCPClientManager().close()


@api.post('/ocr/<int:agent_id>', 
    summary="Process OCR", 
    tags=[api_tag],
    responses={"200": OCRResponse}
)
@require_auth
def process_ocr(path: AgentPath):
    
    agent = db.session.query(OCRAgent).filter(OCRAgent.agent_id == path.agent_id).first()
    if agent is None:
        return jsonify({"error": "Agent not found"}), 404
    
    agent.request_count += 1
    db.session.commit()

    if 'pdf' not in request.files:
        logger.error("No PDF file provided in request")
        return jsonify({'error': 'No PDF file provided'}), 400

    pdf_file = request.files['pdf']
    agent_id = request.form.get('agent_id')
    
    if not pdf_file or not agent_id:
        logger.error(f"Incomplete data - pdf_file: {bool(pdf_file)}, agent_id: {agent_id}")
        return jsonify({'error': 'Missing required data'}), 400
    
    # Get paths from environment variables
    downloads_dir = os.getenv('DOWNLOADS_PATH', '/app/temp/downloads/')
    images_dir = os.getenv('IMAGES_PATH', '/app/temp/images/')
    
    logger.info(f"Using directories - downloads: {downloads_dir}, images: {images_dir}")

    os.makedirs(downloads_dir, exist_ok=True)
    os.makedirs(images_dir, exist_ok=True)
        
    # Save PDF temporarily
    pdf_filename = pdf_file.filename
    temp_path = os.path.join(downloads_dir, pdf_filename)
    images_path = os.path.join(images_dir, pdf_filename.split('.')[0])
    
    logger.info(f"Processing file: {pdf_filename}")
    logger.debug(f"Complete paths - temp_path: {temp_path}, images_path: {images_path}")
    
    # Clean up old files if they exist
    if os.path.exists(temp_path):
        logger.info(f"Removing existing temporary file: {temp_path}")
        os.remove(temp_path)
    
    pdf_file.save(temp_path)
    logger.info(f"PDF file saved at: {temp_path}")
    
    try:
        logger.info(f"Starting OCR processing with agent_id: {agent_id}")
        result = process_pdf(int(agent_id), temp_path, images_path)
        logger.info("OCR process completed successfully")
        return jsonify(result)
    except Exception as e:
        logger.error(f"Error during OCR processing: {str(e)}", exc_info=True)
        return jsonify({'error': str(e)}), 500
