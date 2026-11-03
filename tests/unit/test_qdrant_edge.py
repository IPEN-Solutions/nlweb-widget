import pytest

from nlweb_widget.settings import NLWebSettings


def test_qdrant_edge_settings_are_configuration_driven() -> None:
    settings = NLWebSettings(
        _env_file=None,
        retrieval_store="qdrant_edge",
        qdrant_edge_path="./edge-data",
        qdrant_edge_dimensions=384,
    )
    assert settings.qdrant_edge_path == "./edge-data"
    assert settings.qdrant_edge_dimensions == 384


@pytest.mark.asyncio
async def test_qdrant_edge_provider_is_conditional() -> None:
    module = pytest.importorskip("qdrant_edge")
    from nlweb_widget.content.qdrant_edge import QdrantEdgeRetrievalStore

    assert module
    assert QdrantEdgeRetrievalStore


def test_sqlite_settings_are_configuration_driven() -> None:
    settings = NLWebSettings(
        _env_file=None,
        retrieval_store="sqlite",
        sqlite_path="./sqlite-data/nlweb.db",
        sqlite_dimensions=384,
    )
    assert settings.sqlite_path == "./sqlite-data/nlweb.db"
    assert settings.sqlite_dimensions == 384
