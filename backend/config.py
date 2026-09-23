import math
import os
from dotenv import load_dotenv
from typing import Optional
from pydantic import BaseModel

load_dotenv()

from utils.secret_key import get_secret_key  # noqa: E402 – must follow load_dotenv()

class ClientConfig(BaseModel):
    client_id: str
    client_name: str
    oidc_enabled: bool = True
    oidc_authority: Optional[str] = None
    oidc_client_id: Optional[str] = None
    custom_domain: Optional[str] = None
    
def load_client_config() -> ClientConfig:
    """Load client configuration from environment variables."""
    login_mode = os.getenv('AICT_LOGIN', 'OIDC').upper()
    oidc_enabled = (login_mode == 'OIDC')
    
    return ClientConfig(
        client_id=os.getenv('CLIENT_ID', 'default'),
        client_name=os.getenv('CLIENT_NAME', 'Mattin AI'),
        oidc_enabled=oidc_enabled,
        oidc_authority=os.getenv('OIDC_AUTHORITY'),
        oidc_client_id=os.getenv('OIDC_CLIENT_ID'),
        custom_domain=os.getenv('CUSTOM_DOMAIN')
    )

CLIENT_CONFIG = load_client_config()

DATABASE_URL = os.getenv('SQLALCHEMY_DATABASE_URI', 'postgresql://iacoretoolsdev:iacoretoolsdev@localhost:5432/iacoretoolsdev')

# Fails fast at import if SECRET_KEY is absent, too short, or a known weak value.
SECRET_KEY: str = get_secret_key()
GOOGLE_CLIENT_ID = os.getenv('GOOGLE_CLIENT_ID', '')
GOOGLE_CLIENT_SECRET = os.getenv('GOOGLE_CLIENT_SECRET', '')

VECTOR_DB_TYPE = os.getenv('VECTOR_DB_TYPE', 'PGVECTOR').upper()

QDRANT_URL = os.getenv('QDRANT_URL', 'http://localhost:6333')
QDRANT_API_KEY = os.getenv('QDRANT_API_KEY')
QDRANT_PREFER_GRPC = os.getenv('QDRANT_PREFER_GRPC', 'false').lower() == 'true'

PINECONE_API_KEY = os.getenv('PINECONE_API_KEY')
PINECONE_ENVIRONMENT = os.getenv('PINECONE_ENVIRONMENT')

WEAVIATE_URL = os.getenv('WEAVIATE_URL')
WEAVIATE_API_KEY = os.getenv('WEAVIATE_API_KEY')

CHROMA_PERSIST_DIR = os.getenv('CHROMA_PERSIST_DIR', './chroma_db')

# MCP Server Configuration
# Base URL for generating MCP endpoint URLs (e.g., https://your-domain.com)
MCP_BASE_URL = os.getenv('MCP_BASE_URL', 'http://localhost:8000')

# ---------------------------------------------------------------------------
# Sandbox provider configuration (IT-2)
# ---------------------------------------------------------------------------

# System-wide default provider when an app has no explicit sandbox_provider.
# Allowed values: 'opensandbox' (self-hosted), 'daytona' (managed SaaS),
# 'e2b' (managed cloud).
SANDBOX_DEFAULT_PROVIDER = os.getenv('SANDBOX_DEFAULT_PROVIDER', 'opensandbox').lower()

# Comma-separated list of provider names apps may select in this deployment.
SANDBOX_ALLOWED_PROVIDERS = [
    p.strip()
    for p in os.getenv('SANDBOX_ALLOWED_PROVIDERS', 'opensandbox,daytona,e2b').split(',')
    if p.strip()
]

# OpenSandbox server connection.
OPENSANDBOX_DOMAIN = os.getenv('OPENSANDBOX_DOMAIN', 'localhost:8080')
OPENSANDBOX_API_KEY = os.getenv('OPENSANDBOX_API_KEY', '')
OPENSANDBOX_CODE_INTERPRETER_IMAGE = os.getenv(
    'OPENSANDBOX_CODE_INTERPRETER_IMAGE',
    'opensandbox/code-interpreter:v1.0.2',
)

# Timeout for creating/reconnecting a sandbox (seconds).
SANDBOX_CREATE_TIMEOUT_S = int(os.getenv('SANDBOX_CREATE_TIMEOUT_S', '60'))

# Per-execution timeout (seconds).
SANDBOX_DEFAULT_TIMEOUT_S = int(os.getenv('SANDBOX_DEFAULT_TIMEOUT_S', '30'))

# Timeout for a skill's bootstrap script (seconds). Deliberately generous (and
# distinct from SANDBOX_DEFAULT_TIMEOUT_S): bootstrap scripts are explicitly permitted to
# assume network egress (e.g. `pip install`) to prepare a skill's runtime dependencies
# (product decision, see skills-boosted plan Decision 12 — this is not an oversight).
SANDBOX_SKILL_BOOTSTRAP_TIMEOUT_S = int(os.getenv('SANDBOX_SKILL_BOOTSTRAP_TIMEOUT_S', '120'))

# Maximum sandbox session lifetime (hours).
SANDBOX_SESSION_TTL_H = float(os.getenv('SANDBOX_SESSION_TTL_H', '2'))

# Maximum idle time before cached sandboxes are stopped/destroyed (seconds).
SANDBOX_IDLE_TIMEOUT_S = int(os.getenv('SANDBOX_IDLE_TIMEOUT_S', '120'))

# How often the in-process sandbox reaper checks for idle sandboxes (seconds).
SANDBOX_REAPER_INTERVAL_S = int(os.getenv('SANDBOX_REAPER_INTERVAL_S', '30'))

# Maximum number of characters returned by run_code (truncates at this limit).
SANDBOX_MAX_OUTPUT_CHARS = int(os.getenv('SANDBOX_MAX_OUTPUT_CHARS', '20000'))

# Maximum number of REPL executions per agent turn (budget guard).
SANDBOX_MAX_EXECUTIONS_PER_TURN = int(os.getenv('SANDBOX_MAX_EXECUTIONS_PER_TURN', '5'))

# Maximum number of OpenSandbox code contexts created per language in one
# sandbox. Values above 1 allow parallel tool executions without sharing a busy
# interpreter session.
OPENSANDBOX_MAX_CONTEXTS_PER_LANGUAGE = int(os.getenv('OPENSANDBOX_MAX_CONTEXTS_PER_LANGUAGE', '4'))

# Daytona SaaS sandbox connection and creation options. The Daytona SDK also
# reads DAYTONA_API_KEY, DAYTONA_API_URL, and DAYTONA_TARGET directly from the
# environment; these constants document the integration surface.
DAYTONA_API_KEY = os.getenv('DAYTONA_API_KEY', '')
DAYTONA_API_URL = os.getenv('DAYTONA_API_URL', '')
DAYTONA_TARGET = os.getenv('DAYTONA_TARGET', '')
DAYTONA_IMAGE = os.getenv('DAYTONA_IMAGE', '')
DAYTONA_SNAPSHOT = os.getenv('DAYTONA_SNAPSHOT', '')
DAYTONA_WORKSPACE = os.getenv('DAYTONA_WORKSPACE', 'workspace')

# E2B cloud sandbox connection and creation options. The E2B SDK reads
# E2B_API_KEY directly from the environment.
E2B_API_KEY = os.getenv('E2B_API_KEY', '')
E2B_TEMPLATE = os.getenv('E2B_TEMPLATE', '')
E2B_WORKSPACE = os.getenv('E2B_WORKSPACE', '/home/user/workspace')

# Minutes before a sandbox TTL is proactively renewed.
SANDBOX_RENEW_MINUTES = int(os.getenv('SANDBOX_RENEW_MINUTES', '30'))

# --- Skill package import limits (hardened zip reader, backend/utils/safe_zip.py) ---
def _env_int(name: str, default: int, *, minimum: int = 1) -> int:
    """Read an integer env var, failing fast on unparsable or below-minimum values."""
    raw = os.getenv(name)
    if raw is None or raw.strip() == '':
        return default
    try:
        value = int(raw.strip())
    except ValueError:
        raise RuntimeError(f"Invalid {name}={raw!r}: expected an integer >= {minimum}") from None
    if value < minimum:
        raise RuntimeError(f"Invalid {name}={raw!r}: expected an integer >= {minimum}")
    return value


def _env_float(name: str, default: float, *, minimum: float, finite: bool = True, inclusive: bool = True) -> float:
    """Read a float env var, failing fast on unparsable, non-finite or out-of-range values.

    ``inclusive=False`` makes ``minimum`` an exclusive bound (value must be strictly greater).
    """
    raw = os.getenv(name)
    if raw is None or raw.strip() == '':
        return default
    bound = f">= {minimum}" if inclusive else f"> {minimum}"
    try:
        value = float(raw.strip())
    except ValueError:
        raise RuntimeError(f"Invalid {name}={raw!r}: expected a finite number {bound}") from None
    if finite and not math.isfinite(value):
        raise RuntimeError(f"Invalid {name}={raw!r}: expected a finite number {bound}")
    if math.isnan(value) or value < minimum or (not inclusive and value == minimum):
        raise RuntimeError(f"Invalid {name}={raw!r}: expected a finite number {bound}")
    return value


# Maximum number of file entries in an uploaded skill package.
SKILL_IMPORT_MAX_FILES = _env_int('SKILL_IMPORT_MAX_FILES', 500)
# Maximum cumulative uncompressed size of an uploaded skill package (bytes).
SKILL_IMPORT_MAX_TOTAL_BYTES = _env_int('SKILL_IMPORT_MAX_TOTAL_BYTES', 50 * 1024 * 1024)
# Maximum uncompressed size of a single file inside a skill package (bytes).
SKILL_IMPORT_MAX_FILE_BYTES = _env_int('SKILL_IMPORT_MAX_FILE_BYTES', 10 * 1024 * 1024)
# Maximum uncompressed/compressed ratio (zip bomb guard), measured against the uploaded archive size.
SKILL_IMPORT_MAX_RATIO = _env_float('SKILL_IMPORT_MAX_RATIO', 100.0, minimum=1.0, inclusive=False)
# Maximum size of the uploaded (compressed) archive itself (bytes).
SKILL_IMPORT_MAX_ARCHIVE_BYTES = _env_int('SKILL_IMPORT_MAX_ARCHIVE_BYTES', 25 * 1024 * 1024)
# Maximum number of skill package operations (import OR export) processed concurrently per backend
# process — both hold a whole skill's files in memory at once, so they share this bulkhead.
SKILL_IMPORT_MAX_CONCURRENCY = _env_int('SKILL_IMPORT_MAX_CONCURRENCY', 2)
