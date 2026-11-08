from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    GEMINI_API_KEY: str
    CHROMA_PERSIST_DIR: str = "./db"
    COLLECTION_NAME: str = "knowledge_base"
    EMBEDDING_MODEL: str = "gemini-embedding-001"
    LLM_MODEL: str = "gemini-2.5-flash"

    # Automatically load environment variables from the .env file
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

# Instantiate settings as a singleton across the app
settings = Settings()