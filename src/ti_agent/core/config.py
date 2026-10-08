"""Application settings and 12-factor environment configuration."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central configuration loaded from environment variables and .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # Threat Intelligence Providers
    vt_api_key: str | None = Field(
        default=None,
        description="VirusTotal API v3 key",
    )
    shodan_api_key: str | None = Field(
        default=None,
        description="Shodan API key",
    )
    nvd_api_key: str | None = Field(
        default=None,
        description="NIST NVD API 2.0 key",
    )

    # LLM Settings
    llm_provider: Literal["openai", "anthropic", "ollama"] = Field(
        default="ollama",
        description="Configured LLM provider",
    )
    openai_api_key: str | None = Field(
        default=None,
        description="OpenAI API key",
    )
    openai_model: str = Field(
        default="gpt-4o-mini",
        description="OpenAI model identifier",
    )
    anthropic_api_key: str | None = Field(
        default=None,
        description="Anthropic API key",
    )
    anthropic_model: str = Field(
        default="claude-3-5-sonnet-20241022",
        description="Anthropic model identifier",
    )
    ollama_base_url: str = Field(
        default="http://localhost:11434",
        description="Ollama local API base URL",
    )
    ollama_model: str = Field(
        default="llama3.1:8b",
        description="Ollama model identifier",
    )

    # RAG Settings
    embedding_provider: str = Field(
        default="sentence-transformers",
        description="Embedding provider name",
    )
    embedding_model: str = Field(
        default="all-MiniLM-L6-v2",
        description="Embedding model name",
    )
    chroma_persist_dir: Path = Field(
        default=Path("./data/chroma"),
        description="Directory for persisting ChromaDB vectorstore",
    )
    rag_top_k: int = Field(
        default=4,
        ge=1,
        le=20,
        description="Default number of chunks retrieved by RAG",
    )

    # Cache Settings
    cache_dir: Path = Field(
        default=Path("./.cache/diskcache"),
        description="Diskcache directory path",
    )
    cache_ttl_seconds: int = Field(
        default=86400,
        ge=0,
        description="Cache Time-To-Live in seconds (default 24h)",
    )
    enable_cache: bool = Field(
        default=True,
        description="Enable/disable API response caching",
    )
    offline_mode: bool = Field(
        default=False,
        description="Offline mode using local recorded fixtures",
    )

    # Execution Guards
    max_iterations: int = Field(
        default=10,
        ge=1,
        le=50,
        description="Maximum supervisor routing iterations",
    )
    max_tokens_per_execution: int = Field(
        default=50000,
        ge=1000,
        description="Maximum cumulative tokens budget per agent run",
    )
    log_level: str = Field(
        default="INFO",
        description="Logging level (DEBUG, INFO, WARNING, ERROR)",
    )


@lru_cache
def get_settings() -> Settings:
    """Retrieve cached application settings instance."""
    return Settings()
