from flask import request
from flask_openapi3 import Tag
from api.api_auth import require_auth
from utils.pricing_decorators import check_api_usage_limit
from utils.error_handlers import handle_api_errors
from api.pydantic.agent_pydantic import AgentPath, DetachFilePath
from api.files.service import FileService

# Import the api blueprint from the main api module
from api.api import api

api_tag = Tag(name="API", description="Main API endpoints")


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
    return FileService.attach_file(path.agent_id, request.files.get('file'))


@api.delete('/detach-file/<int:agent_id>/<file_reference>', 
    summary="Remove attached file", 
    tags=[api_tag],
    responses={"200": {"description": "File removed successfully"}}
)
@require_auth
@handle_api_errors(include_traceback=False)
def detach_file(path: DetachFilePath):
    """
    Remove an attached file from the session.
    """
    return FileService.detach_file(path.agent_id, path.file_reference)


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
    return FileService.list_attached_files(path.agent_id) 