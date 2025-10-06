from fastapi import APIRouter, Depends

# Import all public v1 routers
from .agents import agents_router
from .chat import chat_router
from .files import files_router
from .ocr import ocr_router
from .repositories import repositories_router
from .resources import resources_router
from .silos import silos_router
from .rate_limit import enforce_app_rate_limit
from .origins import enforce_allowed_origins

# Create the main public v1 router
public_v1_router = APIRouter()

# Include sub-routers with proper app structure: /public/v1/app/{app_id}/...
# Apply rate limiting and origin validation to execution-heavy endpoints
public_v1_router.include_router(agents_router, prefix="/app/{app_id}/agents", dependencies=[Depends(enforce_allowed_origins)])
public_v1_router.include_router(chat_router, prefix="/app/{app_id}/chat", dependencies=[Depends(enforce_app_rate_limit), Depends(enforce_allowed_origins)])
public_v1_router.include_router(files_router, prefix="/app/{app_id}/files", dependencies=[Depends(enforce_allowed_origins)])
public_v1_router.include_router(ocr_router, prefix="/app/{app_id}/ocr", dependencies=[Depends(enforce_app_rate_limit), Depends(enforce_allowed_origins)])
public_v1_router.include_router(repositories_router, prefix="/app/{app_id}/repositories", dependencies=[Depends(enforce_allowed_origins)])
public_v1_router.include_router(resources_router, prefix="/app/{app_id}/resources", dependencies=[Depends(enforce_allowed_origins)])
public_v1_router.include_router(silos_router, prefix="/app/{app_id}/silos", dependencies=[Depends(enforce_allowed_origins)])
