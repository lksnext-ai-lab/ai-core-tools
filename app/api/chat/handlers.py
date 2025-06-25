import json
from flask import request, current_app
from api.pydantic.agent_pydantic import AgentPath, ChatRequest
from api.chat.service import ChatService
from api.files.utils import FileUtils
from api.files.service import FileService
from api.shared.agent_utils import AgentUtils
from api.shared.session_utils import SessionUtils
from utils.logger import get_logger
from utils.error_handlers import ValidationError, NotFoundError

logger = get_logger(__name__)


class ChatRequestHandler:
    @staticmethod
    def handle_call(path: AgentPath, body: ChatRequest):
        """Main entry point for chat requests."""
        # Check if this is a multipart form request
        if request.content_type and 'multipart/form-data' in request.content_type:
            return ChatRequestHandler._handle_multipart_request(path)
        
        # Handle JSON request with potential base64 attachment
        return ChatRequestHandler._handle_json_request(path, body)

    @staticmethod
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
                attachment_path = FileUtils.process_file_upload(request.files['file'])
            
            # Get agent
            agent = ChatService.get_agent(path.agent_id)
            if agent is None:
                raise NotFoundError(f"Agent with ID {path.agent_id} not found", "agent")
            
            logger.info(f"Processing multipart request for agent {agent.agent_id}: {question[:50]}...")
            
            # Update request count
            ChatService.update_request_count(agent)
            
            # Setup tracer if configured
            tracer = AgentUtils.setup_tracer(agent)
            
            # Process agent request with attachment
            result = current_app.ensure_sync(ChatService.process_agent_request_with_attachments)(
                agent, question, tracer, search_params, attachment_path, None
            )
            
            # Handle response format
            if isinstance(result, tuple) and len(result) == 2 and isinstance(result[1], int):
                return result
            
            # Successful response - store in session
            SessionUtils.add_message_to_session(result["generated_text"])
            
            logger.info(f"Successfully processed multipart request for agent {agent.agent_id}")
            return result
            
        except Exception as e:
            logger.error(f"Error in multipart request: {str(e)}", exc_info=True)
            raise

    @staticmethod
    def _handle_json_request(path: AgentPath, body: ChatRequest):
        """Handle JSON requests with potential base64 attachments and file references."""
        # Validate input
        if not body.question or not body.question.strip():
            raise ValidationError("Question cannot be empty")
        
        question = body.question.strip()
        
        # Process base64 attachment if present
        attachment_path = None
        if body.attachment:
            attachment_path = FileUtils.process_base64_attachment(
                body.attachment, 
                body.attachment_filename or "attachment", 
                body.attachment_mime_type or "application/octet-stream"
            )
        
        # Process file references if present
        file_references = body.file_references or []
        referenced_files = FileService.get_referenced_files(path.agent_id, file_references)
        
        # Get agent
        agent = ChatService.get_agent(path.agent_id)
        if agent is None:
            raise NotFoundError(f"Agent with ID {path.agent_id} not found", "agent")
        
        logger.info(f"Processing JSON request for agent {agent.agent_id}: {question[:50]}...")
        
        # Update request count if not already counted by the usage limit decorator
        ChatService.update_request_count(agent)
        
        # Setup tracer if configured
        tracer = AgentUtils.setup_tracer(agent)
        
        # Process agent request with attachments
        result = current_app.ensure_sync(ChatService.process_agent_request_with_attachments)(
            agent, question, tracer, body.search_params, attachment_path, referenced_files
        )
        
        # Handle response format
        if isinstance(result, tuple) and len(result) == 2 and isinstance(result[1], int):
            # Error response tuple
            return result
        
        # Successful response - store in session
        SessionUtils.add_message_to_session(result["generated_text"])
        
        logger.info(f"Successfully processed JSON request for agent {agent.agent_id}")
        return result 