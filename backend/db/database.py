from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import create_async_engine, AsyncEngine
from sqlalchemy.orm import sessionmaker, declarative_base, Session
from typing import Generator
import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv('SQLALCHEMY_DATABASE_URI')
if not DATABASE_URL:
    raise EnvironmentError("SQLALCHEMY_DATABASE_URI environment variable is required")

# Total connections per process = (sync pool + async pool + checkpointer pool)
# x workers x replicas. Keep below Postgres max_connections (default 100).
# pool_timeout is short on purpose: a saturated pool fails fast as 503 (main.py)
# rather than blocking 30s. All tunable via env without a code change.
DB_POOL_SIZE = int(os.getenv('DB_POOL_SIZE', '20'))
DB_MAX_OVERFLOW = int(os.getenv('DB_MAX_OVERFLOW', '10'))
DB_POOL_TIMEOUT = int(os.getenv('DB_POOL_TIMEOUT', '10'))
DB_POOL_RECYCLE = int(os.getenv('DB_POOL_RECYCLE', '3600'))

# Configure synchronous engine with connection pooling for better concurrency
engine = create_engine(
    DATABASE_URL,
    pool_size=DB_POOL_SIZE,           # Number of connections to maintain in the pool
    max_overflow=DB_MAX_OVERFLOW,     # Additional connections allowed when pool is full
    pool_timeout=DB_POOL_TIMEOUT,     # Fail fast instead of blocking 30s when saturated
    pool_pre_ping=True,               # Verify connections before using them
    pool_recycle=DB_POOL_RECYCLE,     # Recycle connections (prevent stale connections)
    echo=False,                       # Set to True for SQL debugging
    connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
)

# Configure async engine for async operations (needed for async retrievers in LangGraph)
# Use psycopg (async) instead of asyncpg to avoid "cannot insert multiple commands" limitation
# psycopg supports async natively and handles multiple SQL statements properly
ASYNC_DATABASE_URL = DATABASE_URL.replace('postgresql://', 'postgresql+psycopg://') if DATABASE_URL.startswith('postgresql://') else DATABASE_URL
async_engine = create_async_engine(
    ASYNC_DATABASE_URL,
    pool_size=DB_POOL_SIZE,
    max_overflow=DB_MAX_OVERFLOW,
    pool_timeout=DB_POOL_TIMEOUT,
    pool_pre_ping=True,
    pool_recycle=DB_POOL_RECYCLE,
    echo=False,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db() -> Generator[Session, None, None]:
    """
    Database dependency that provides a SQLAlchemy session.
    This is the proper way to handle database sessions in FastAPI.
    """
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()

class Database:
    """Exposes the shared engines to the vector-store factory.

    Engines only — no module-level Session (that would pin a pool connection for
    the whole process). Sessions are request- or task-scoped via get_db/SessionLocal.
    """

    def __init__(self):
        self.engine = engine
        self._async_engine = async_engine  # Async engine for vector operations

db = Database()