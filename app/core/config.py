import os

from dotenv import load_dotenv


load_dotenv()


DATABASE_URL = os.getenv("DATABASE_URL")
HEALTH_ENCRYPTION_KEY = os.getenv("HEALTH_ENCRYPTION_KEY")
