from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import create_async_engine, AsyncEngine
from sqlalchemy.orm import sessionmaker, declarative_base, Session
from typing import Generator
import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv('SQLALCHEMY_DATABASE_URI', 'postgresql://iacore:iacore@localhost:5432/iacore')

# Configure synchronous engine with connection pooling for better concurrency
engine = create_engine(
    DATABASE_URL, 
    pool_size=20,              # Number of connections to maintain in the pool
    max_overflow=10,           # Additional connections allowed when pool is full
    pool_pre_ping=True,        # Verify connections before using them
    pool_recycle=3600,         # Recycle connections after 1 hour (prevent stale connections)
    echo=False,                # Set to True for SQL debugging
    connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
)

# Configure async engine for async operations (needed for async retrievers in LangGraph)
# Use psycopg (async) instead of asyncpg to avoid "cannot insert multiple commands" limitation
# psycopg supports async natively and handles multiple SQL statements properly
ASYNC_DATABASE_URL = DATABASE_URL.replace('postgresql://', 'postgresql+psycopg://') if DATABASE_URL.startswith('postgresql://') else DATABASE_URL
async_engine = create_async_engine(
    ASYNC_DATABASE_URL,
    pool_size=20,
    max_overflow=10,
    pool_pre_ping=True,
    pool_recycle=3600,
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
    def __init__(self):
        self.engine = engine
        self._async_engine = async_engine  # Async engine for vector operations
        self.session = SessionLocal()

db = Database()