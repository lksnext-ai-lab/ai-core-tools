'''This file is used to create the database connection.'''
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import create_engine
#import os


#DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///default.db")
#some_engine = create_engine(DATABASE_URL)
#db = SQLAlchemy(session_options={'bind': some_engine})
db = SQLAlchemy()
