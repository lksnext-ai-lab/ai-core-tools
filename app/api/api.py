from flask_openapi3 import APIBlueprint, Tag

# Main API blueprint setup
api_tag = Tag(name="API", description="Main API endpoints")
security=[{"api_key":[]}]
api = APIBlueprint('api', __name__, url_prefix='/api/app/<int:app_id>',abp_security=security)

# Import all routes from the modular structure
# This ensures all routes are registered with the blueprint
from api.chat.routes import *
from api.files.routes import *
from api.ocr.routes import * 