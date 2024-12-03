'''This file is used to create the database connection.'''
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import create_engine
from dotenv import load_dotenv
import os
from db.base_class import Base

load_dotenv()

MYSQL_USER = os.getenv("MYSQL_USER")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD")
MYSQL_HOST = os.getenv("MYSQL_HOST")
MYSQL_SCHEMA = os.getenv("MYSQL_SCHEMA")
DATABASE_URL = f"mysql+pymysql://{MYSQL_USER}:{MYSQL_PASSWORD}@{MYSQL_HOST}/{MYSQL_SCHEMA}"
print(DATABASE_URL)
some_engine = create_engine(DATABASE_URL)
db = SQLAlchemy(session_options={'bind': some_engine})

def init_db():
    """Inicializa la base de datos y crea todas las tablas si no existen"""
    try:
        # Verifica si hay tablas existentes
        inspector = db.inspect(some_engine)
        existing_tables = inspector.get_table_names()
        
        if existing_tables:
            print(f"Tablas existentes encontradas: {', '.join(existing_tables)}")
            return
            
        Base.metadata.create_all(bind=some_engine)
        print("Base de datos inicializada correctamente")
    except Exception as e:
        print(f"Error al inicializar la base de datos: {str(e)}")
