import pytest
from pydantic import ValidationError

from nlweb_widget.settings import NLWebSettings


def test_disabled_by_default() -> None:
    settings = NLWebSettings(_env_file=None)
    assert settings.enabled is False


def test_pgvector_requires_database_url() -> None:
    with pytest.raises(ValidationError, match="NLWEB_POSTGRES_DATABASE_URL"):
        NLWebSettings(_env_file=None, retrieval_store="pgvector")


def test_neo4j_requires_connection_fields() -> None:
    with pytest.raises(ValidationError, match="NLWEB_NEO4J_PASSWORD"):
        NLWebSettings(
            _env_file=None,
            retrieval_store="neo4j",
            neo4j_uri="neo4j://localhost:7687",
            neo4j_username="neo4j",
        )


def test_startup_sync_requires_sync_enabled() -> None:
    with pytest.raises(ValidationError, match="NLWEB_CONTENT_SYNC_ON_STARTUP"):
        NLWebSettings(
            _env_file=None, content_sync_enabled=False, content_sync_on_startup=True
        )
