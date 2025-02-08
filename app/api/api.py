from flask import session, request, jsonify
from flask_openapi3 import APIBlueprint, Tag
from pydantic import BaseModel
from app.agents.ocrAgent import process_pdf
from app.model.agent import Agent
import app.tools.modelTools as modelTools
from app.extensions import db
import os
import logging
from app.api.api_auth import require_auth
from app.agents.ocrAgent import OCRAgent
from app.api.pydantic.agent_pydantic import AgentPath, ChatRequest
# Logging configuration
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

api_tag = Tag(name="API", description="Main API endpoints")
api = APIBlueprint('api', __name__, url_prefix='/api/app/<int:app_id>')

MSG_LIST = "MSG_LIST"


@api.post('/call/<int:agent_id>', summary="Call agent", tags=[api_tag])
@require_auth
def call_agent(path: AgentPath, body: ChatRequest):
    question = body.question
    agent = db.session.query(Agent).filter(Agent.agent_id == path.agent_id).first()
    
    if agent is None:
        return jsonify({"error": "Agent not found"}), 404
    
    if agent.request_count is None:
        agent.request_count = 0
    agent.request_count += 1
    db.session.commit()

    result = ""
    if agent.has_memory:
        result = modelTools.invoke_ConversationalRetrievalChain(agent, question, session)
    elif agent.silo is not None:
        result = modelTools.invoke_with_RAG(agent, question)
    else:
        result = modelTools.invoke(agent, question)

    data = {
        "input": question,
        "generated_text": result,
        "control": {
            "temperature": 0.8,
            "max_tokens": 100,
            "top_p": 0.9,
            "frequency_penalty": 0.5,
            "presence_penalty": 0.5,
            "stop_sequence": "\n\n"
        },
        "metadata": {
            "model_name": agent.model.name,
            "timestamp": "2024-04-04T12:00:00Z"
        }
    }

    if MSG_LIST not in session:
        session[MSG_LIST] = []
    session[MSG_LIST].append(result)

    return jsonify(data)

@api.post('/ocr', summary="Process OCR", tags=[api_tag])
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
    