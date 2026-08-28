"""Application settings, loaded from environment variables and .env.

One Settings object is built at import time and cached. Everything that needs
configuration imports `settings` from here rather than reading os.environ, so
there is exactly one place where a setting's name, type and default live.
"""

from functools import lru_cache
from typing import Literal

from pydantic import computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",  # .env carries frontend/crawler keys the API ignores
    )

    # --- Application -------------------------------------------------------
    app_name: str = "PCE Knowledge Management System"
    app_env: Literal["development", "production"] = "development"
    debug: bool = True
    log_level: str = "INFO"
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    api_prefix: str = "/api/v1"

    # Comma-separated in the environment; exposed as a list via cors_origin_list.
    cors_origins: str = "http://localhost:3000"

    # --- Security ----------------------------------------------------------
    secret_key: str = "dev-only-insecure-key-change-me"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7
    jwt_algorithm: str = "HS256"

    # Seed admin account. The seed refuses to create a user while the
    # password is still the placeholder from .env.example.
    admin_email: str = "admin@pce.local"
    admin_password: str = "change_this_before_first_run"

    # --- PostgreSQL --------------------------------------------------------
    postgres_user: str = "pce"
    postgres_password: str = "pce_dev_password"
    postgres_db: str = "pce_kms"
    postgres_host: str = "localhost"
    postgres_port: int = 5432

    # --- Redis -------------------------------------------------------------
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 0

    # --- ChromaDB ----------------------------------------------------------
    chroma_host: str = "localhost"
    chroma_port: int = 8000
    chroma_collection: str = "pce_chunks"

    # --- Ollama ------------------------------------------------------------
    ollama_base_url: str = "http://localhost:11434"
    ollama_generator_model: str = "qwen2.5:7b-instruct-q4_K_M"
    ollama_judge_model: str = "llama3.1:8b-instruct-q4_K_M"
    llm_temperature: float = 0.1
    llm_max_tokens: int = 1024
    llm_timeout_seconds: int = 180

    # --- Embeddings / reranking -------------------------------------------
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    embedding_dimension: int = 384
    reranker_model: str = "BAAI/bge-reranker-base"

    # --- Retrieval defaults ------------------------------------------------
    chunk_min_tokens: int = 256
    chunk_max_tokens: int = 800
    chunk_overlap_ratio: float = 0.15
    dense_top_k: int = 20
    sparse_top_k: int = 20
    rrf_k: int = 60
    rerank_top_n: int = 5
    agent_max_iterations: int = 3
    agent_timeout_seconds: int = 120

    # --- Paths -------------------------------------------------------------
    corpus_dir: str = "./corpus"
    data_dir: str = "./data"

    # --- Ablation flags: all false == configuration C0, the naive baseline --
    rag_structure_aware_chunking: bool = True
    rag_hybrid_retrieval: bool = True
    rag_reranking: bool = True
    rag_agentic_layer: bool = True
    rag_verification: bool = True

    # --- Derived -----------------------------------------------------------
    @computed_field  # type: ignore[prop-decorator]
    @property
    def database_url(self) -> str:
        return (
            f"postgresql+psycopg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @computed_field  # type: ignore[prop-decorator]
    @property
    def redis_url(self) -> str:
        return f"redis://{self.redis_host}:{self.redis_port}/{self.redis_db}"

    @computed_field  # type: ignore[prop-decorator]
    @property
    def chroma_url(self) -> str:
        return f"http://{self.chroma_host}:{self.chroma_port}"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"


@lru_cache
def get_settings() -> Settings:
    """Cached accessor. Tests override this via FastAPI dependency_overrides."""
    return Settings()


settings: Settings = get_settings()

__all__ = ["Settings", "get_settings", "settings"]
