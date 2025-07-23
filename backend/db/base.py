from sqlalchemy.orm import declarative_base
from db.session import engine, SessionLocal

Base = declarative_base()

# Simple database object for PGVectorTools compatibility
class Database:
    def __init__(self):
        self.engine = engine
        self.session = SessionLocal()

# Create a global database instance
db = Database() 