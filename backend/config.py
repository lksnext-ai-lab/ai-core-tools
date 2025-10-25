import os
from dotenv import load_dotenv
from typing import Optional
from pydantic import BaseModel

load_dotenv()

class ClientConfig(BaseModel):
    client_id: str
    client_name: str
    oidc_enabled: bool = False
    oidc_authority: Optional[str] = None
    oidc_client_id: Optional[str] = None
    custom_domain: Optional[str] = None
    
def load_client_config() -> ClientConfig:
    """Load client configuration from environment variables"""
    return ClientConfig(
        client_id=os.getenv('CLIENT_ID', 'default'),
        client_name=os.getenv('CLIENT_NAME', 'Mattin AI'),
        oidc_enabled=os.getenv('OIDC_ENABLED', 'false').lower() == 'true',
        oidc_authority=os.getenv('OIDC_AUTHORITY'),
        oidc_client_id=os.getenv('OIDC_CLIENT_ID'),
        custom_domain=os.getenv('CUSTOM_DOMAIN')
    )

CLIENT_CONFIG = load_client_config()

DATABASE_URL = os.getenv('SQLALCHEMY_DATABASE_URI', 'postgresql://iacoretoolsdev:iacoretoolsdev@localhost:5432/iacoretoolsdev')
SECRET_KEY = os.getenv('SECRET_KEY', 'supersecret')
GOOGLE_CLIENT_ID = os.getenv('GOOGLE_CLIENT_ID', '')
GOOGLE_CLIENT_SECRET = os.getenv('GOOGLE_CLIENT_SECRET', '') 