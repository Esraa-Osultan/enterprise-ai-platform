"""
Central configuration for the whole app.

Everything that can change between environments (dev, staging, prod)
lives here and nowhere else, so we never end up with a magic string
buried three files deep.
"""

from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # --- App ---
    app_name: str = "Enterprise AI Knowledge & Engineering Assistant"
    environment: str = "development"
    debug: bool = True

    # --- Auth ---
    jwt_secret_key: str = "change-this-secret-in-production"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60

    # --- Storage paths ---
    upload_dir: str = "data/uploads"
    vector_store_dir: str = "data/vector_store"
    users_db_path: str = "data/users.json"

    # --- RAG / Embeddings ---
    # "hash" works fully offline and is deterministic (good for tests/CI).
    # "sentence-transformers" gives real semantic search but needs network
    # access the first time it downloads the model weights.
    embedding_backend: str = "hash"
    embedding_model_name: str = "all-MiniLM-L6-v2"
    embedding_dim: int = 384

    chunk_size: int = 800
    chunk_overlap: int = 120
    top_k: int = 4

    # --- LLM (answer generation) ---
    # If no API key is set, the pipeline falls back to an extractive
    # answer built directly from the retrieved chunks, so the app is
    # still usable end-to-end in a demo with zero external calls.
    openai_api_key: str = ""
    llm_model_name: str = "gpt-4o-mini"

    # --- Logging ---
    log_level: str = "INFO"
    log_file: str = "data/app.log"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


@lru_cache
def get_settings() -> Settings:
    """Settings are read once and cached; call get_settings() everywhere
    instead of instantiating Settings() directly."""
    return Settings()
