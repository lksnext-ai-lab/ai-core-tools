from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base, Session
from typing import Generator
import os
from dotenv import load_dotenv

load_dotenv()

# Database configuration
DATABASE_URL = os.getenv('SQLALCHEMY_DATABASE_URI', 'postgresql://iacore:iacore@localhost:5432/iacore')

# Engine configuration
engine = create_engine(
    DATABASE_URL, 
    connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
)

# Session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base class for models
Base = declarative_base()

# Database dependency for FastAPI
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

# Simple database object for compatibility
class Database:
    def __init__(self):
        self.engine = engine
        self.session = SessionLocal()

# Create a global database instance
db = Database()