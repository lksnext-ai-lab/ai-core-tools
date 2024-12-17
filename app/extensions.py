'''This file is used to create the database connection.'''
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import create_engine
import os
from app.db.base_class import Base

DATABASE_URL = f"postgresql+psycopg://{os.getenv('DATABASE_USER')}:{os.getenv('DATABASE_PASSWORD')}@{os.getenv('DATABASE_HOST')}:{os.getenv('DATABASE_PORT')}/{os.getenv('DATABASE_NAME')}"
some_engine = create_engine(DATABASE_URL)
db = SQLAlchemy(session_options={'bind': some_engine})

def init_db():
    """Inicializa la base de datos"""
    try:
        inspector = db.inspect(some_engine)
        existing_tables = inspector.get_table_names()
        
        if existing_tables:
            print(f"Tablas existentes encontradas: {', '.join(existing_tables)}")
            return
            
        Base.metadata.create_all(bind=some_engine)
        print("Base de datos inicializada correctamente")
    except Exception as e:
        print(f"Error al inicializar la base de datos: {str(e)}")
