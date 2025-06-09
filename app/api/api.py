from flask import session, request, jsonify, current_app
from flask_openapi3 import APIBlueprint, Tag
from agents.ocrAgent import process_pdf
from model.agent import Agent
from extensions import db
import os
import json
from api.api_auth import require_auth
from utils.pricing_decorators import check_api_usage_limit
from agents.ocrAgent import OCRAgent
from api.pydantic.agent_pydantic import AgentPath, ChatRequest, AgentResponse, OCRResponse
from tools.agentTools import create_agent, MCPClientManager
from langchain_core.messages import HumanMessage, AIMessage
from langchain.callbacks.tracers import LangChainTracer
from langsmith import Client
from services.agent_cache_service import AgentCacheService
from typing import Optional
from pydantic import BaseModel, conint
import uuid
import pathlib

# Use centralized logging
from utils.logger import get_logger
from utils.error_handlers import (
    handle_api_errors, NotFoundError, ValidationError, safe_execute,
    validate_required_fields, validate_field_types
)

logger = get_logger(__name__)

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
@check_api_usage_limit('api_calls')
@handle_api_errors(include_traceback=False)
def call_agent(path: AgentPath, body: ChatRequest):
    """
    Entry point for agent calls that ensures the connection remains
    open until the agent response is complete.
    """
    # Validate input
    if not body.question or not body.question.strip():
        raise ValidationError("Question cannot be empty")
    
    question = body.question.strip()
    
    # Get agent
    agent = db.session.query(Agent).filter(Agent.agent_id == path.agent_id).first()
    if agent is None:
        raise NotFoundError(f"Agent with ID {path.agent_id} not found", "agent")
    
    logger.info(f"Processing request for agent {agent.agent_id}: {question[:50]}...")
    
    # Update request count if not already counted by the usage limit decorator
    if not hasattr(request, 'api_usage_already_counted'):
        agent.request_count = (agent.request_count or 0) + 1
        result, error = safe_execute(db.session.commit, log_errors=True)
        if error:
            logger.warning(f"Failed to update request count: {error}")
    
    # Setup tracer if configured
    tracer = None
    if agent.app.langsmith_api_key:
        client = Client(api_key=agent.app.langsmith_api_key)
        tracer = LangChainTracer(client=client, project_name=agent.app.name)
    
    # Process agent request
    result = current_app.ensure_sync(process_agent_request)(agent, question, tracer)
    
    # Handle response format
    if isinstance(result, tuple) and len(result) == 2 and isinstance(result[1], int):
        # Error response tuple
        return result
    
    # Successful response - store in session
    if MSG_LIST not in session:
        session[MSG_LIST] = []
    session[MSG_LIST].append(result["generated_text"])
    
    logger.info(f"Successfully processed request for agent {agent.agent_id}")
    return result


async def _get_or_create_agent(agent):
    """Helper function to get cached agent or create new one."""
    agent_x = None
    if agent.has_memory:
        agent_x = AgentCacheService.get_cached_agent(agent.agent_id)
    
    if agent_x is None:
        logger.info("Creating new agent instance")
        agent_x = await create_agent(agent)
        if agent.has_memory:
            AgentCacheService.cache_agent(agent.agent_id, agent_x)
            logger.info("Agent cached successfully")
        else:
            logger.info("Agent not cached as it has no memory enabled")
    return agent_x

def _prepare_agent_config(agent, tracer):
    """Helper function to prepare agent configuration."""
    config = {
        "configurable": {
            "thread_id": f"thread_{agent.agent_id}"
        },
        "recursion_limit": 200,
    }
    if tracer is not None:
        config["callbacks"] = [tracer]
    return config

def _parse_agent_response(response_text, agent):
    """Helper function to parse agent response."""
    if agent.output_parser_id is not None:
        content = response_text.strip()
        if content.startswith('```json'):
            content = content[7:]
        if content.endswith('```'):
            content = content[:-3]
        content = content.strip()
        try:
            return json.loads(content)
        except json.JSONDecodeError as e:
            logger.error(f"Error parsing JSON response: {e}")
            return response_text
    return response_text

async def process_agent_request(agent, question, tracer):
    """
    Processes the agent request asynchronously with improved structure.
    """
    try:
        logger.info(f"Processing agent request for agent {agent.agent_id}: {question[:50]}...")
        
        # Get or create agent instance
        agent_x = await _get_or_create_agent(agent)
        
        # Prepare configuration
        config = _prepare_agent_config(agent, tracer)
        
        # Invoke agent
        result = await agent_x.ainvoke(
            {"messages": [{"role": "user", "content": f"{question}"}]}, 
            config
        )
        logger.info("Agent response received")
        
        # Extract response
        final_message = next(
            (msg for msg in reversed(result['messages']) if isinstance(msg, AIMessage)), 
            None
        )
        response_text = final_message.content if final_message else str(result)
        
        # Parse response
        parsed_response = _parse_agent_response(response_text, agent)
        
        # Prepare response data
        return {
            "input": question,
            "generated_text": parsed_response,
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
    
    except Exception as e:
        logger.error(f"Error processing agent request: {str(e)}", exc_info=True)
        return {"error": str(e)}, 500
    finally:
        await MCPClientManager().close()


class OCRRequest(BaseModel):
    agent_id: int

    @classmethod
    def __get_validators__(cls):
        yield from super().__get_validators__()
        yield cls.validate_agent_id

    @staticmethod
    def validate_agent_id(value):
        if value <= 0:
            raise ValueError("agent_id must be a positive integer")
        return value


@api.post('/ocr/<int:agent_id>', 
    summary="Process OCR", 
    tags=[api_tag],
    responses={"200": OCRResponse}
)
@require_auth
@check_api_usage_limit('api_calls')
@handle_api_errors(include_traceback=False)
def process_ocr(path: AgentPath):
    # Validate agent_id from form data
    raw_agent_id = request.form.get('agent_id')
    if not raw_agent_id:
        raise ValidationError('Missing agent_id parameter')
    
    try:
        validated_data = OCRRequest(agent_id=int(raw_agent_id))
        agent_id = validated_data.agent_id
    except (ValueError, TypeError):
        raise ValidationError('Invalid agent_id format')
    
    # Get OCR agent
    agent = db.session.query(OCRAgent).filter(OCRAgent.agent_id == agent_id).first()
    if agent is None:
        raise NotFoundError(f"OCR Agent with ID {agent_id} not found", "ocr_agent")
    
    # Update request count if not already counted by the usage limit decorator
    if not hasattr(request, 'api_usage_already_counted'):
        agent.request_count = (agent.request_count or 0) + 1
        result, error = safe_execute(db.session.commit, log_errors=True)
        if error:
            logger.warning(f"Failed to update request count: {error}")
    
    # Validate PDF file upload
    if 'pdf' not in request.files:
        raise ValidationError('No PDF file provided')
    
    pdf_file = request.files['pdf']
    if not pdf_file or not pdf_file.filename:
        raise ValidationError('Missing or empty PDF file')
    
    # Validate file extension
    original_filename = pdf_file.filename
    file_ext = pathlib.Path(original_filename).suffix.lower()
    if file_ext != '.pdf':
        raise ValidationError('Only PDF files are allowed')
    
    # Generate secure filename
    secure_filename = f"{uuid.uuid4()}{file_ext}"
    
    # Get paths from environment variables with defaults
    downloads_dir = os.getenv('DOWNLOADS_PATH', '/app/temp/downloads/')
    images_dir = os.getenv('IMAGES_PATH', '/app/temp/images/')
    
    # Ensure directories exist
    os.makedirs(downloads_dir, exist_ok=True)
    os.makedirs(images_dir, exist_ok=True)
    
    # Setup file paths
    temp_path = os.path.join(downloads_dir, secure_filename)
    images_path = os.path.join(images_dir, secure_filename[:-4])  # remove .pdf
    
    logger.info(f"Processing OCR for file: {secure_filename} with agent {agent_id}")
    
    # Clean up old files if they exist
    if os.path.exists(temp_path):
        safe_execute(os.remove, temp_path, log_errors=False)
    
    # Save PDF file
    pdf_file.save(temp_path)
    
    try:
        logger.info("Starting OCR processing with agent")
        result = process_pdf(int(agent_id), temp_path, images_path)
        logger.info("OCR process completed successfully")
        return jsonify(result)
    except Exception as e:
        logger.error(f"Error during OCR processing: {str(e)}", exc_info=True)
        # Clean up files on error
        safe_execute(os.remove, temp_path, log_errors=False)
        raise
