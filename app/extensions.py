'''This file is used to create the database connection.'''
import asyncio
import sys
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.ext.asyncio import AsyncSession
import os
from db.base_class import Base
from dotenv import load_dotenv

# Configure event loop policy for Windows
if sys.platform.startswith('win'):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

load_dotenv()

# Import logger and config utilities after dotenv to ensure environment variables are loaded
from utils.logger import get_logger
from utils.error_handlers import DatabaseError
from utils.config import get_database_url, get_async_database_url

logger = get_logger(__name__)

# Create sync engine with validated configuration
DATABASE_URL = get_database_url()
engine = create_engine(DATABASE_URL)
db = SQLAlchemy(session_options={'bind': engine})

# Create async engine with validated configuration
ASYNC_DATABASE_URL = get_async_database_url()
async_engine = create_async_engine(ASYNC_DATABASE_URL)

def init_db():
    """Initialize the database"""
    try:
        inspector = db.inspect(engine)
        existing_tables = inspector.get_table_names()
        if existing_tables:
            logger.info(f"Existing tables found: {', '.join(existing_tables)}")
            return
        
        logger.info("Creating database tables...")
        Base.metadata.create_all(bind=engine)
        logger.info("Database initialized successfully")
        
    except Exception as e:
        logger.error(f"Error initializing database: {str(e)}", exc_info=True)
        raise DatabaseError(f"Failed to initialize database: {str(e)}", "init_db")
