import os
from dotenv import load_dotenv

# Force reload .env every time this module is imported (on uvicorn hot-reload)
load_dotenv(override=True)

class Settings:
    @property
    def GROQ_API_KEY(self):
        return os.getenv("GROQ_API_KEY", "")

    @property
    def OPENAI_API_KEY(self):
        return os.getenv("OPENAI_API_KEY", "")

    REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
    DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./2care.db")
    PORT = int(os.getenv("PORT", 8000))

settings = Settings()
