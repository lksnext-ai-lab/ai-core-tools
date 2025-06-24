from flask import session, request, jsonify, current_app
from flask_openapi3 import APIBlueprint, Tag
from agents.ocrAgent import process_pdf
from model.agent import Agent
from extensions import db
import os
import json
import base64
import tempfile
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


def _process_base64_attachment(attachment: str, filename: str, mime_type: str) -> Optional[str]:
    """
    Process base64 encoded attachment and save to temporary file.
    Returns the path to the temporary file.
    """
    try:
        # Remove data URL prefix if present
        if attachment.startswith('data:'):
            # Extract base64 data after the comma
            attachment = attachment.split(',', 1)[1]
        
        # Decode base64 data
        file_data = base64.b64decode(attachment)
        
        # Create temporary file
        temp_dir = os.getenv('DOWNLOADS_PATH', '/app/temp/downloads/')
        os.makedirs(temp_dir, exist_ok=True)
        
        # Generate secure filename
        secure_filename = f"{uuid.uuid4()}_{filename}"
        temp_path = os.path.join(temp_dir, secure_filename)
        
        # Write file data
        with open(temp_path, 'wb') as f:
            f.write(file_data)
        
        logger.info(f"Saved base64 attachment to: {temp_path}")
        return temp_path
        
    except Exception as e:
        logger.error(f"Error processing base64 attachment: {str(e)}")
        raise ValidationError(f"Invalid attachment format: {str(e)}")


def _process_file_upload(file) -> Optional[str]:
    """
    Process uploaded file and save to temporary location.
    Returns the path to the temporary file.
    """
    try:
        if not file or not file.filename:
            return None
        
        # Validate file extension
        original_filename = file.filename
        file_ext = pathlib.Path(original_filename).suffix.lower()
        allowed_extensions = ['.pdf', '.txt', '.doc', '.docx', '.png', '.jpg', '.jpeg']
        
        if file_ext not in allowed_extensions:
            raise ValidationError(f'File type {file_ext} not allowed. Allowed types: {", ".join(allowed_extensions)}')
        
        # Create temporary file
        temp_dir = os.getenv('DOWNLOADS_PATH', '/app/temp/downloads/')
        os.makedirs(temp_dir, exist_ok=True)
        
        # Generate secure filename
        secure_filename = f"{uuid.uuid4()}{file_ext}"
        temp_path = os.path.join(temp_dir, secure_filename)
        
        # Save file
        file.save(temp_path)
        
        logger.info(f"Saved uploaded file to: {temp_path}")
        return temp_path
        
    except Exception as e:
        logger.error(f"Error processing file upload: {str(e)}")
        raise ValidationError(f"Error processing file: {str(e)}")


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
    Supports both JSON requests with base64 attachments and multipart form data.
    """
    # Check if this is a multipart form request
    if request.content_type and 'multipart/form-data' in request.content_type:
        return _handle_multipart_request(path)
    
    # Handle JSON request with potential base64 attachment
    return _handle_json_request(path, body)


def _handle_multipart_request(path: AgentPath):
    """Handle multipart form data requests with file uploads."""
    try:
        # Extract form data
        question = request.form.get('question')
        if not question or not question.strip():
            raise ValidationError("Question cannot be empty")
        
        question = question.strip()
        
        # Parse search params if provided
        search_params = None
        if request.form.get('search_params'):
            try:
                search_params = json.loads(request.form.get('search_params'))
            except json.JSONDecodeError:
                raise ValidationError("Invalid search_params JSON format")
        
        # Process file upload if present
        attachment_path = None
        if 'file' in request.files:
            attachment_path = _process_file_upload(request.files['file'])
        
        # Get agent
        agent = db.session.query(Agent).filter(Agent.agent_id == path.agent_id).first()
        if agent is None:
            raise NotFoundError(f"Agent with ID {path.agent_id} not found", "agent")
        
        logger.info(f"Processing multipart request for agent {agent.agent_id}: {question[:50]}...")
        
        # Update request count
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
        
        # Process agent request with attachment
        result = current_app.ensure_sync(process_agent_request_with_attachments)(
            agent, question, tracer, search_params, attachment_path, None
        )
        
        # Handle response format
        if isinstance(result, tuple) and len(result) == 2 and isinstance(result[1], int):
            return result
        
        # Successful response - store in session
        if MSG_LIST not in session:
            session[MSG_LIST] = []
        session[MSG_LIST].append(result["generated_text"])
        
        logger.info(f"Successfully processed multipart request for agent {agent.agent_id}")
        return result
        
    except Exception as e:
        logger.error(f"Error in multipart request: {str(e)}", exc_info=True)
        raise


def _handle_json_request(path: AgentPath, body: ChatRequest):
    """Handle JSON requests with potential base64 attachments and file references."""
    # Validate input
    if not body.question or not body.question.strip():
        raise ValidationError("Question cannot be empty")
    
    question = body.question.strip()
    
    # Process base64 attachment if present
    attachment_path = None
    if body.attachment:
        attachment_path = _process_base64_attachment(
            body.attachment, 
            body.attachment_filename or "attachment", 
            body.attachment_mime_type or "application/octet-stream"
        )
    
    # Process file references if present
    file_references = body.file_references or []
    referenced_files = []
    
    if file_references:
        attached_files = session.get('attached_files', {})
        for file_ref in file_references:
            if file_ref in attached_files:
                file_info = attached_files[file_ref]
                # Verify the file is for this agent
                if file_info.get('agent_id') == path.agent_id and os.path.exists(file_info['path']):
                    referenced_files.append(file_info)
                else:
                    logger.warning(f"File reference {file_ref} not found or invalid for agent {path.agent_id}")
            else:
                logger.warning(f"File reference {file_ref} not found in session")
    
    # Get agent
    agent = db.session.query(Agent).filter(Agent.agent_id == path.agent_id).first()
    if agent is None:
        raise NotFoundError(f"Agent with ID {path.agent_id} not found", "agent")
    
    logger.info(f"Processing JSON request for agent {agent.agent_id}: {question[:50]}...")
    
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
    
    # Process agent request with attachments
    result = current_app.ensure_sync(process_agent_request_with_attachments)(
        agent, question, tracer, body.search_params, attachment_path, referenced_files
    )
    
    # Handle response format
    if isinstance(result, tuple) and len(result) == 2 and isinstance(result[1], int):
        # Error response tuple
        return result
    
    # Successful response - store in session
    if MSG_LIST not in session:
        session[MSG_LIST] = []
    session[MSG_LIST].append(result["generated_text"])
    
    logger.info(f"Successfully processed JSON request for agent {agent.agent_id}")
    return result


async def _get_or_create_agent(agent, search_params=None):
    """Helper function to get cached agent or create new one."""
    agent_x = None
    if agent.has_memory:
        agent_x = AgentCacheService.get_cached_agent(agent.agent_id)
    
    if agent_x is None:
        logger.info("Creating new agent instance")
        agent_x = await create_agent(agent, search_params)
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

async def process_agent_request_with_attachments(agent, question, tracer, search_params, attachment_path=None, referenced_files=None):
    """
    Processes the agent request asynchronously with support for multiple file attachments.
    """
    try:
        logger.info(f"Processing agent request with attachments for agent {agent.agent_id}: {question[:50]}...")
        
        # Get or create agent instance
        agent_x = await _get_or_create_agent(agent, search_params)
        
        # Prepare configuration
        config = _prepare_agent_config(agent, tracer)
        
        # Prepare message content
        message_content = question
        
        # Process base64 attachment if present
        if attachment_path:
            attachment_content = _process_attachment_for_agent(attachment_path, agent)
            message_content += attachment_content
            logger.info(f"Processed base64 attachment: {attachment_path}")
        
        # Process referenced files if present
        if referenced_files:
            for file_info in referenced_files:
                attachment_content = _process_attachment_for_agent(file_info['path'], agent)
                message_content += attachment_content
                logger.info(f"Processed referenced file: {file_info['filename']}")
        
        # Invoke agent
        result = await agent_x.ainvoke(
            {"messages": [{"role": "user", "content": message_content}]}, 
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
        
        # Clean up base64 attachment file if it was created
        if attachment_path and os.path.exists(attachment_path):
            try:
                os.remove(attachment_path)
                logger.info(f"Cleaned up base64 attachment file: {attachment_path}")
            except Exception as e:
                logger.warning(f"Failed to clean up base64 attachment file {attachment_path}: {e}")
        
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
                "timestamp": "2024-04-04T12:00:00Z",
                "attachments_processed": (attachment_path is not None) or (referenced_files is not None and len(referenced_files) > 0),
                "attachment_count": (1 if attachment_path else 0) + (len(referenced_files) if referenced_files else 0)
            }
        }
    
    except Exception as e:
        logger.error(f"Error processing agent request with attachments: {str(e)}", exc_info=True)
        # Clean up base64 attachment file on error
        if attachment_path and os.path.exists(attachment_path):
            try:
                os.remove(attachment_path)
                logger.info(f"Cleaned up base64 attachment file on error: {attachment_path}")
            except Exception as cleanup_error:
                logger.warning(f"Failed to clean up base64 attachment file on error {attachment_path}: {cleanup_error}")
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

@api.post('/reset/<int:agent_id>', 
    summary="Reset conversation", 
    tags=[api_tag],
    responses={"200": {"description": "Conversation reset successfully"}}
)
@require_auth
@handle_api_errors(include_traceback=False)
def reset_conversation(path: AgentPath):
    """
    Resets the conversation state for the current session and clears agent cache.
    """
    # Clear the message list from session
    if MSG_LIST in session:
        session[MSG_LIST] = []
        session.modified = True
    
    # Clear the agent from cache
    AgentCacheService.invalidate_agent(path.agent_id)
    
    logger.info(f"Reset conversation and cleared cache for agent {path.agent_id}")
    return {"status": "success", "message": "Conversation reset successfully"}

def _process_attachment_for_agent(attachment_path: str, agent) -> str:
    """
    Process attachment file and return appropriate content for the agent.
    Handles different file types (PDF, images, text files) based on agent capabilities.
    """
    try:
        if not attachment_path or not os.path.exists(attachment_path):
            return ""
        
        file_ext = pathlib.Path(attachment_path).suffix.lower()
        
        # Handle PDF files
        if file_ext == '.pdf':
            return _process_pdf_attachment(attachment_path, agent)
        
        # Handle image files
        elif file_ext in ['.png', '.jpg', '.jpeg']:
            return _process_image_attachment(attachment_path, agent)
        
        # Handle text files
        elif file_ext in ['.txt', '.md']:
            return _process_text_attachment(attachment_path)
        
        # Handle document files (basic text extraction)
        elif file_ext in ['.doc', '.docx']:
            return _process_document_attachment(attachment_path)
        
        else:
            logger.warning(f"Unsupported file type: {file_ext}")
            return f"\n\n[Unsupported file type: {file_ext}]"
            
    except Exception as e:
        logger.error(f"Error processing attachment {attachment_path}: {str(e)}")
        return f"\n\n[Error processing attachment: {str(e)}]"


def _process_pdf_attachment(pdf_path: str, agent) -> str:
    """Process PDF attachment using OCR if available."""
    try:
        # Check if agent has OCR capabilities
        if hasattr(agent, 'has_ocr') and agent.has_ocr:
            # Use existing OCR functionality
            images_dir = os.getenv('IMAGES_PATH', '/app/temp/images/')
            images_path = os.path.join(images_dir, f"{uuid.uuid4()}")
            
            result = process_pdf(agent.agent_id, pdf_path, images_path)
            if result and 'text' in result:
                return f"\n\n[PDF Content: {result['text'][:1000]}...]"  # Limit text length
        
        # Fallback: just mention the PDF
        return f"\n\n[PDF file attached: {os.path.basename(pdf_path)}]"
        
    except Exception as e:
        logger.error(f"Error processing PDF {pdf_path}: {str(e)}")
        return f"\n\n[PDF file attached: {os.path.basename(pdf_path)}]"


def _process_image_attachment(image_path: str, agent) -> str:
    """Process image attachment for vision models."""
    try:
        # Check if agent has vision capabilities
        if hasattr(agent, 'vision_service_rel') and agent.vision_service_rel:
            # Convert image to base64 for vision models
            import base64
            with open(image_path, 'rb') as img_file:
                img_data = base64.b64encode(img_file.read()).decode('utf-8')
            
            # For vision models, we'll include the base64 data
            # The agent processing will need to handle this appropriately
            return f"\n\n[Image data: data:image/jpeg;base64,{img_data[:100]}...]"
        
        # Fallback: just mention the image
        return f"\n\n[Image file attached: {os.path.basename(image_path)}]"
        
    except Exception as e:
        logger.error(f"Error processing image {image_path}: {str(e)}")
        return f"\n\n[Image file attached: {os.path.basename(image_path)}]"


def _process_text_attachment(text_path: str) -> str:
    """Process text file attachment."""
    try:
        with open(text_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Limit content length to avoid overwhelming the agent
        max_length = 2000
        if len(content) > max_length:
            content = content[:max_length] + "..."
        
        return f"\n\n[Text file content: {content}]"
        
    except Exception as e:
        logger.error(f"Error processing text file {text_path}: {str(e)}")
        return f"\n\n[Text file attached: {os.path.basename(text_path)}]"


def _process_document_attachment(doc_path: str) -> str:
    """Process document file attachment (basic implementation)."""
    try:
        # For now, just mention the document
        # In a full implementation, you might use libraries like python-docx
        return f"\n\n[Document file attached: {os.path.basename(doc_path)}]"
        
    except Exception as e:
        logger.error(f"Error processing document {doc_path}: {str(e)}")
        return f"\n\n[Document file attached: {os.path.basename(doc_path)}]"


@api.post('/attach-file/<int:agent_id>', 
    summary="Attach file for chat", 
    tags=[api_tag],
    responses={"200": {"description": "File attached successfully"}}
)
@require_auth
@check_api_usage_limit('api_calls')
@handle_api_errors(include_traceback=False)
def attach_file(path: AgentPath):
    """
    Upload a file for use in chat conversations.
    Returns a file reference that can be used in subsequent chat messages.
    """
    try:
        # Get agent
        agent = db.session.query(Agent).filter(Agent.agent_id == path.agent_id).first()
        if agent is None:
            raise NotFoundError(f"Agent with ID {path.agent_id} not found", "agent")
        
        # Validate file upload
        if 'file' not in request.files:
            raise ValidationError('No file provided')
        
        file = request.files['file']
        if not file or not file.filename:
            raise ValidationError('Missing or empty file')
        
        # Process file upload
        attachment_path = _process_file_upload(file)
        if not attachment_path:
            raise ValidationError('Failed to process file upload')
        
        # Generate file reference
        file_reference = str(uuid.uuid4())
        
        # Store file reference in session (or database in production)
        if 'attached_files' not in session:
            session['attached_files'] = {}
        
        session['attached_files'][file_reference] = {
            'path': attachment_path,
            'filename': file.filename,
            'content_type': file.content_type,
            'agent_id': path.agent_id,
            'uploaded_at': '2024-04-04T12:00:00Z'  # In production, use actual timestamp
        }
        session.modified = True
        
        logger.info(f"File attached for agent {path.agent_id}: {file.filename} -> {file_reference}")
        
        return {
            "status": "success",
            "file_reference": file_reference,
            "filename": file.filename,
            "content_type": file.content_type,
            "message": "File attached successfully"
        }
        
    except Exception as e:
        logger.error(f"Error attaching file: {str(e)}", exc_info=True)
        raise


@api.delete('/detach-file/<int:agent_id>/<file_reference>', 
    summary="Remove attached file", 
    tags=[api_tag],
    responses={"200": {"description": "File removed successfully"}}
)
@require_auth
@handle_api_errors(include_traceback=False)
def detach_file(path: AgentPath, file_reference: str):
    """
    Remove an attached file from the session.
    """
    try:
        # Get agent
        agent = db.session.query(Agent).filter(Agent.agent_id == path.agent_id).first()
        if agent is None:
            raise NotFoundError(f"Agent with ID {path.agent_id} not found", "agent")
        
        # Check if file exists in session
        if 'attached_files' not in session or file_reference not in session['attached_files']:
            raise NotFoundError(f"File reference {file_reference} not found", "file")
        
        file_info = session['attached_files'][file_reference]
        
        # Clean up file from disk
        if os.path.exists(file_info['path']):
            try:
                os.remove(file_info['path'])
                logger.info(f"Removed file from disk: {file_info['path']}")
            except Exception as e:
                logger.warning(f"Failed to remove file from disk: {e}")
        
        # Remove from session
        del session['attached_files'][file_reference]
        session.modified = True
        
        logger.info(f"File detached for agent {path.agent_id}: {file_reference}")
        
        return {
            "status": "success",
            "message": "File removed successfully"
        }
        
    except Exception as e:
        logger.error(f"Error detaching file: {str(e)}", exc_info=True)
        raise


@api.get('/attached-files/<int:agent_id>', 
    summary="List attached files", 
    tags=[api_tag],
    responses={"200": {"description": "List of attached files"}}
)
@require_auth
@handle_api_errors(include_traceback=False)
def list_attached_files(path: AgentPath):
    """
    List all files attached to the current session for this agent.
    """
    try:
        # Get agent
        agent = db.session.query(Agent).filter(Agent.agent_id == path.agent_id).first()
        if agent is None:
            raise NotFoundError(f"Agent with ID {path.agent_id} not found", "agent")
        
        # Get attached files from session
        attached_files = session.get('attached_files', {})
        
        # Filter files for this agent
        agent_files = {
            ref: info for ref, info in attached_files.items() 
            if info.get('agent_id') == path.agent_id
        }
        
        # Clean up references to non-existent files
        valid_files = {}
        for ref, info in agent_files.items():
            if os.path.exists(info['path']):
                valid_files[ref] = {
                    'filename': info['filename'],
                    'content_type': info['content_type'],
                    'uploaded_at': info['uploaded_at']
                }
            else:
                # Remove invalid reference
                if 'attached_files' in session and ref in session['attached_files']:
                    del session['attached_files'][ref]
        
        session.modified = True
        
        return {
            "status": "success",
            "files": valid_files,
            "count": len(valid_files)
        }
        
    except Exception as e:
        logger.error(f"Error listing attached files: {str(e)}", exc_info=True)
        raise
