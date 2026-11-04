from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class NLWebSettings(BaseSettings):
    """Framework-neutral runtime settings with conditional provider validation."""

    model_config = SettingsConfigDict(
        env_prefix="NLWEB_",
        env_file=Path.cwd() / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    enabled: bool = False
    prefix: str = "/nlweb"
    public_base_url: str = "http://localhost:8000"
    site: str = "default"
    retrieval_store: Literal[
        "memory",
        "haystack",
        "haystack-memory",
        "pgvector",
        "neo4j",
        "qdrant",
        "qdrant_edge",
        "sqlite",
        "custom",
    ] = "memory"
    postgres_database_url: str | None = None
    pgvector_dimensions: int = Field(default=384, ge=1, le=16_000)
    pgvector_table: str = "nlweb_documents"
    postgres_auto_initialize: bool = True
    qdrant_url: str | None = None
    qdrant_api_key: str | None = None
    qdrant_collection: str = "nlweb_documents"
    qdrant_dimensions: int = Field(default=384, ge=1, le=65_535)
    qdrant_auto_initialize: bool = True
    qdrant_edge_path: str = "./.nlweb-qdrant-edge"
    qdrant_edge_dimensions: int = Field(default=384, ge=1, le=65_535)
    sqlite_path: str = "./.nlweb-sqlite/nlweb.db"
    sqlite_dimensions: int = Field(default=384, ge=1, le=65_535)
    embedding_model: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    embedding_query_prefix: str | None = None
    embedding_document_prefix: str | None = None
    embedding_device: str | None = "cpu"
    neo4j_uri: str | None = None
    neo4j_username: str | None = None
    neo4j_password: str | None = None
    neo4j_database: str = "neo4j"
    neo4j_vector_index: str = "nlweb_document_embedding"
    neo4j_vector_dimensions: int = Field(default=384, ge=1, le=4096)
    neo4j_auto_initialize: bool = True
    content_sync_enabled: bool = True
    content_sources_file: str = "./nlweb-sources.json"
    content_sync_state_file: str = ".nlweb-sync-state.json"
    content_sync_interval_seconds: float = Field(default=900.0, ge=0, le=86_400)
    content_sync_on_startup: bool = False

    @model_validator(mode="after")
    def validate_dependencies(self) -> "NLWebSettings":
        if self.retrieval_store == "pgvector" and not self.postgres_database_url:
            raise ValueError(
                "NLWEB_POSTGRES_DATABASE_URL is required when "
                "NLWEB_RETRIEVAL_STORE=pgvector"
            )
        if self.retrieval_store == "qdrant" and not self.qdrant_url:
            raise ValueError(
                "NLWEB_QDRANT_URL is required when NLWEB_RETRIEVAL_STORE=qdrant"
            )
        if self.retrieval_store == "qdrant_edge" and not self.qdrant_edge_path.strip():
            raise ValueError(
                "NLWEB_QDRANT_EDGE_PATH is required when NLWEB_RETRIEVAL_STORE=qdrant_edge"
            )
        if self.retrieval_store == "sqlite" and not self.sqlite_path.strip():
            raise ValueError(
                "NLWEB_SQLITE_PATH is required when NLWEB_RETRIEVAL_STORE=sqlite"
            )
        if self.retrieval_store == "neo4j":
            missing = [
                name
                for name, value in {
                    "NLWEB_NEO4J_URI": self.neo4j_uri,
                    "NLWEB_NEO4J_USERNAME": self.neo4j_username,
                    "NLWEB_NEO4J_PASSWORD": self.neo4j_password,
                }.items()
                if not value
            ]
            if missing:
                raise ValueError("Neo4j retrieval requires: " + ", ".join(missing))
        if self.content_sync_on_startup and not self.content_sync_enabled:
            raise ValueError(
                "NLWEB_CONTENT_SYNC_ON_STARTUP requires NLWEB_CONTENT_SYNC_ENABLED=true"
            )
        if self.content_sync_enabled and not self.content_sources_file.strip():
            raise ValueError(
                "NLWEB_CONTENT_SOURCES_FILE is required when content synchronization is enabled"
            )
        return self


@lru_cache(maxsize=1)
def get_settings() -> NLWebSettings:
    return NLWebSettings()
