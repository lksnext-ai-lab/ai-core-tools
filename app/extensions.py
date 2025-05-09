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

# Create sync engine
DATABASE_URL = f"postgresql+psycopg://{os.getenv('DATABASE_USER')}:{os.getenv('DATABASE_PASSWORD')}@{os.getenv('DATABASE_HOST')}:{os.getenv('DATABASE_PORT')}/{os.getenv('DATABASE_NAME')}"
engine = create_engine(DATABASE_URL)
db = SQLAlchemy(session_options={'bind': engine})

# Create async engine
ASYNC_DATABASE_URL = f"postgresql+psycopg_async://{os.getenv('DATABASE_USER')}:{os.getenv('DATABASE_PASSWORD')}@{os.getenv('DATABASE_HOST')}:{os.getenv('DATABASE_PORT')}/{os.getenv('DATABASE_NAME')}"
async_engine = create_async_engine(ASYNC_DATABASE_URL)

def init_db():
    """Inicializa la base de datos"""
    try:
        inspector = db.inspect(engine)
        existing_tables = inspector.get_table_names()
        if existing_tables:
            print(f"Tablas existentes encontradas: {', '.join(existing_tables)}")
            return
        Base.metadata.create_all(bind=engine)
        print("Base de datos inicializada correctamente")
    except Exception as e:
        print(f"Error al inicializar la base de datos: {str(e)}")
