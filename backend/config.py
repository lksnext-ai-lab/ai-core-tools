import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv('SQLALCHEMY_DATABASE_URI', 'postgresql://iacoretoolsdev:iacoretoolsdev@localhost:5432/iacoretoolsdev')
SECRET_KEY = os.getenv('SECRET_KEY', 'supersecret')
GOOGLE_CLIENT_ID = os.getenv('GOOGLE_CLIENT_ID', '')
GOOGLE_CLIENT_SECRET = os.getenv('GOOGLE_CLIENT_SECRET', '') 