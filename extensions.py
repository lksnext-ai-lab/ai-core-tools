'''This file is used to create the database connection.'''
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import create_engine

some_engine = create_engine('mysql://LKSSemanticSearch:LKSSemanticSearch@localhost/LKSSemanticSearch',
                            pool_recycle=3600)

db = SQLAlchemy(session_options={'bind': some_engine})
