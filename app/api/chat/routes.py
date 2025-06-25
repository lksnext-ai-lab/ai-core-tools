from flask_openapi3 import Tag
from api.api_auth import require_auth
from utils.pricing_decorators import check_api_usage_limit
from utils.error_handlers import handle_api_errors
from api.pydantic.agent_pydantic import AgentPath, ChatRequest, AgentResponse
from api.chat.handlers import ChatRequestHandler
from api.chat.service import ChatService

# Import the api blueprint from the main api module
from api.api import api

api_tag = Tag(name="API", description="Main API endpoints")


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
    return ChatRequestHandler.handle_call(path, body)


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
    return ChatService.reset_conversation(path.agent_id) 