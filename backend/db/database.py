from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base, Session
from typing import Generator
import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv('SQLALCHEMY_DATABASE_URI', 'postgresql://iacore:iacore@localhost:5432/iacore')

engine = create_engine(
    DATABASE_URL, 
    connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
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
        self.session = SessionLocal()

db = Database()