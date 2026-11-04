import os

import pytest

from nlweb_widget import ContentDocument


class _ConfiguredTestEmbedder:
    async def embed(self, texts):
        return [[1.0, 0.5, 0.25, 0.125] for _ in texts]

    async def embed_query(self, texts):
        return [[1.0, 0.5, 0.25, 0.125] for _ in texts]


@pytest.mark.asyncio
async def test_qdrant_provider_is_conditional() -> None:
    url = os.getenv("NLWEB_QDRANT_URL")
    if not url:
        pytest.skip("NLWEB_QDRANT_URL is not configured")
    pytest.importorskip("qdrant_client")
    from nlweb_widget.content.qdrant import QdrantRetrievalStore

    collection = os.getenv("NLWEB_QDRANT_COLLECTION", "nlweb_widget_qc_test") + "_qa"
    store = QdrantRetrievalStore(
        url,
        _ConfiguredTestEmbedder(),
        collection=collection,
        dimensions=4,
        api_key=os.getenv("NLWEB_QDRANT_API_KEY") or None,
    )
    document = ContentDocument(
        id="qdrant-server-optional-test",
        url="https://example.test/qdrant-server-optional-test",
        title="Qdrant Server test",
        content="Qdrant Server optional provider test",
    )
    try:
        await store.initialize()
        assert await store.upsert(document) == 1
        matches = await store.search("Qdrant Server optional provider test", limit=1)
        assert matches and matches[0][0].id == document.id
    finally:
        await store.delete([document.id])
        await store.close()


@pytest.mark.asyncio
async def test_qdrant_edge_provider_is_conditional(tmp_path) -> None:
    path = os.getenv("NLWEB_QDRANT_EDGE_PATH")
    if not path:
        pytest.skip("NLWEB_QDRANT_EDGE_PATH is not configured")
    pytest.importorskip("qdrant_edge")
    from nlweb_widget.content.qdrant_edge import QdrantEdgeRetrievalStore

    test_path = str(tmp_path / "edge")
    store = QdrantEdgeRetrievalStore(test_path, _ConfiguredTestEmbedder(), dimensions=4)
    document = ContentDocument(
        id="11111111-1111-4111-8111-111111111111",
        url="https://example.test/qdrant-edge-optional-test",
        title="Qdrant Edge test",
        content="Qdrant Edge optional provider test",
    )
    await store.upsert(document)
    try:
        await store.initialize()
        matches = await store.search("Qdrant Edge optional provider test", limit=1)
        assert matches and matches[0][0].id == document.id
        # A second operation must reuse the open shard rather than reopening its WAL.
        matches = await store.search("Qdrant Edge optional provider test", limit=1)
        assert matches and matches[0][0].id == document.id
    finally:
        await store.delete([document.id])
        await store.close()


@pytest.mark.asyncio
async def test_haystack_provider_when_explicitly_configured() -> None:
    if os.getenv("NLWEB_RETRIEVAL_STORE") != "haystack-memory":
        pytest.skip("NLWEB_RETRIEVAL_STORE=haystack-memory is not configured")
    pytest.importorskip("haystack")
    from nlweb_widget.content.haystack import HaystackInMemoryRetrievalStore

    store = HaystackInMemoryRetrievalStore(_ConfiguredTestEmbedder())
    document = ContentDocument(
        id="r3-haystack-test",
        url="https://example.test/r3-haystack-test",
        title="Haystack test",
        content="Haystack in-memory optional provider test",
    )
    assert await store.upsert(document) == 1
    matches = await store.search("Haystack in-memory optional provider test", limit=1)
    assert matches and matches[0][0].id == document.id
    await store.close()


@pytest.mark.asyncio
async def test_postgres_provider_when_explicitly_configured() -> None:
    url = os.getenv("NLWEB_POSTGRES_DATABASE_URL")
    if not url:
        pytest.skip("NLWEB_POSTGRES_DATABASE_URL is not configured")
    pytest.importorskip("sqlalchemy")
    from nlweb_widget.content.store import PgVectorStore

    store = PgVectorStore(
        url,
        _ConfiguredTestEmbedder(),
        dimensions=4,
        table="nlweb_test_documents_r2_optional",
    )
    await store.initialize()
    document = ContentDocument(
        id="r2-postgres-optional-test",
        url="https://example.test/r2-postgres-optional-test",
        title="Postgres test",
        content="Postgres pgvector optional provider test",
    )
    try:
        assert await store.upsert(document) == 1
        matches = await store.search(
            "Postgres pgvector optional provider test", limit=1
        )
        assert matches and matches[0][0].id == document.id
    finally:
        await store.delete([document.id])
        await store.close()


@pytest.mark.asyncio
async def test_neo4j_provider_when_explicitly_configured() -> None:
    uri = os.getenv("NLWEB_NEO4J_URI")
    password = os.getenv("NLWEB_NEO4J_PASSWORD")
    if not uri or not password:
        pytest.skip("NLWEB_NEO4J_URI and NLWEB_NEO4J_PASSWORD are not configured")
    pytest.importorskip("neo4j")
    from neo4j import AsyncGraphDatabase

    database = os.getenv("NLWEB_NEO4J_DATABASE", "neo4j").strip() or "neo4j"
    label = "NLWebWidgetR2TestDocument"
    index = "nlweb_widget_r2_test_embedding"
    constraint = "nlweb_widget_r2_test_id"
    driver = AsyncGraphDatabase.driver(
        uri, auth=(os.getenv("NLWEB_NEO4J_USERNAME", "neo4j"), password)
    )
    try:
        await driver.execute_query(
            f"CREATE CONSTRAINT {constraint} IF NOT EXISTS FOR (d:{label}) REQUIRE d.id IS UNIQUE",
            database_=database,
        )
        await driver.execute_query(
            f"CREATE VECTOR INDEX {index} IF NOT EXISTS FOR (d:{label}) ON d.embedding OPTIONS {{ indexConfig: {{ `vector.dimensions`: 4, `vector.similarity_function`: 'cosine' }} }}",
            database_=database,
        )
        await driver.execute_query(
            "SHOW VECTOR INDEXES YIELD name WHERE name = $name RETURN name",
            name=index,
            database_=database,
        )
        await driver.execute_query(
            f"MERGE (d:{label} {{id: $id}}) SET d.embedding=$embedding, d.content=$content",
            id="r2-neo4j-optional-test",
            embedding=[1.0, 0.5, 0.25, 0.125],
            content="Neo4j optional provider test",
            database_=database,
        )
        records, _, _ = await driver.execute_query(
            "CALL db.index.vector.queryNodes($index, 1, $embedding) YIELD node AS d, score RETURN d.id AS id, score",
            index=index,
            embedding=[1.0, 0.5, 0.25, 0.125],
            database_=database,
        )
        assert records and records[0]["id"] == "r2-neo4j-optional-test"
    finally:
        await driver.execute_query(
            f"MATCH (d:{label}) DETACH DELETE d", database_=database
        )
        await driver.close()


@pytest.mark.asyncio
async def test_sqlite_provider_when_explicitly_configured(tmp_path) -> None:
    path = os.getenv("NLWEB_SQLITE_PATH")
    if not path:
        pytest.skip("NLWEB_SQLITE_PATH is not configured")
    pytest.importorskip("sqlite_vec")
    from nlweb_widget.content.sqlite import SQLiteVecRetrievalStore

    store = SQLiteVecRetrievalStore(
        str(tmp_path / "nlweb.db"), _ConfiguredTestEmbedder(), dimensions=4
    )
    document = ContentDocument(
        id="sqlite-optional-test",
        url="https://example.test/sqlite-optional-test",
        title="SQLite test",
        content="SQLite vector keyword optional provider test",
    )
    try:
        assert await store.upsert(document) == 1
        matches = await store.search("SQLite keyword provider", limit=1)
        assert matches and matches[0][0].id == document.id
    finally:
        await store.delete([document.id])
        await store.close()
