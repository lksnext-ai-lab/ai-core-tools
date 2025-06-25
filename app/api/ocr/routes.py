from flask import request
from flask_openapi3 import Tag
from api.api_auth import require_auth
from utils.pricing_decorators import check_api_usage_limit
from utils.error_handlers import handle_api_errors
from api.pydantic.agent_pydantic import AgentPath, OCRResponse
from api.ocr.service import OCRService

# Import the api blueprint from the main api module
from api.api import api

api_tag = Tag(name="API", description="Main API endpoints")


@api.post('/ocr/<int:agent_id>', 
    summary="Process OCR", 
    tags=[api_tag],
    responses={"200": OCRResponse}
)
@require_auth
@check_api_usage_limit('api_calls')
@handle_api_errors(include_traceback=False)
def process_ocr(path: AgentPath):
    """Process OCR for a PDF file."""
    return OCRService.process_ocr(path.agent_id, request.files.get('pdf')) 