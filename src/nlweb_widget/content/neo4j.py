import json
from collections.abc import Sequence
from typing import Any

from ..models import ContentDocument
from .retrieval import EmbeddingProvider, embed_query


class Neo4jKnowledgeGraphStore:
    """Optional Neo4j knowledge-graph and vector retrieval provider."""

    def __init__(
        self,
        uri: str,
        username: str,
        password: str,
        embedding_provider: EmbeddingProvider,
        *,
        database: str = "neo4j",
        dimensions: int = 1536,
        vector_index: str = "nlweb_document_embedding",
    ) -> None:
        try:
            from neo4j import AsyncGraphDatabase
        except ImportError as exc:
            raise RuntimeError("Neo4j support requires the 'neo4j' extra") from exc
        self._database = database
        self._index = _safe_identifier(vector_index)
        self._dimensions = dimensions
        self._embedder = embedding_provider
        self._driver = AsyncGraphDatabase.driver(uri, auth=(username, password))

    async def initialize(self) -> None:
        queries = [
            (
                "CREATE CONSTRAINT nlweb_document_id IF NOT EXISTS "
                "FOR (d:NLWebDocument) REQUIRE d.id IS UNIQUE"
            ),
            (
                "CREATE CONSTRAINT nlweb_entity_key IF NOT EXISTS "
                "FOR (e:NLWebEntity) REQUIRE e.key IS UNIQUE"
            ),
            f"""CREATE VECTOR INDEX {self._index} IF NOT EXISTS
            FOR (d:NLWebDocument) ON d.embedding OPTIONS {{ indexConfig: {{
            `vector.dimensions`: {self._dimensions},
            `vector.similarity_function`: 'cosine' }} }}""",
            "CREATE INDEX nlweb_document_site IF NOT EXISTS FOR (d:NLWebDocument) ON (d.site)",
        ]
        for query in queries:
            await self._driver.execute_query(query, database_=self._database)

    async def upsert(
        self, documents: Sequence[ContentDocument] | ContentDocument
    ) -> int:
        documents = (
            [documents] if isinstance(documents, ContentDocument) else list(documents)
        )
        vectors = await self._embedder.embed(
            [document.content for document in documents]
        )
        if len(vectors) != len(documents):
            raise ValueError(
                "embedding provider returned an incorrect number of vectors"
            )
        for document, vector in zip(documents, vectors, strict=True):
            await self._driver.execute_query(
                """MERGE (d:NLWebDocument {id: $id})
                SET d.url=$url, d.title=$title, d.content=$content, d.site=$site,
                    d.schemaJson=$schema, d.metadataJson=$metadata,
                    d.embedding=$embedding, d.updatedAt=datetime()""",
                id=document.id,
                url=str(document.url),
                title=document.title,
                content=document.content,
                site=document.site or "default",
                schema=json.dumps(document.schema_object, ensure_ascii=False),
                metadata=json.dumps(document.metadata, ensure_ascii=False, default=str),
                embedding=[float(value) for value in vector],
                database_=self._database,
            )
            await self._sync_graph(document)
        return len(documents)

    async def _sync_graph(self, document: ContentDocument) -> None:
        graph = document.metadata.get("graph", {})
        if not isinstance(graph, dict):
            return
        for entity in graph.get("entities", []):
            if not isinstance(entity, dict) or not entity.get("key"):
                continue
            await self._driver.execute_query(
                """MERGE (e:NLWebEntity {key: $key})
                SET e.entityType=$entity_type, e.name=$name, e.url=$url,
                    e.propertiesJson=$properties
                WITH e MATCH (d:NLWebDocument {id: $document_id})
                MERGE (d)-[:MENTIONS]->(e)""",
                key=str(entity["key"]),
                entity_type=str(entity.get("type", "Entity")),
                name=str(entity.get("name", entity["key"])),
                url=entity.get("url"),
                properties=json.dumps(
                    entity.get("properties", {}), ensure_ascii=False, default=str
                ),
                document_id=document.id,
                database_=self._database,
            )
        for relation in graph.get("relationships", []):
            if not isinstance(relation, dict):
                continue
            source = relation.get("source")
            target = relation.get("target")
            rel_type = relation.get("type")
            if not source or not target or not rel_type:
                continue
            relationship = _safe_identifier(str(rel_type)).upper()
            await self._driver.execute_query(
                f"""MATCH (a:NLWebEntity {{key: $source}}), (b:NLWebEntity {{key: $target}})
                MERGE (a)-[r:{relationship}]->(b)
                SET r.propertiesJson=$properties""",
                source=str(source),
                target=str(target),
                properties=json.dumps(
                    relation.get("properties", {}), ensure_ascii=False, default=str
                ),
                database_=self._database,
            )

    async def delete(self, ids: Sequence[str]) -> int:
        if not ids:
            return 0
        records, _, _ = await self._driver.execute_query(
            """MATCH (d:NLWebDocument) WHERE d.id IN $ids
            WITH collect(d) AS docs, count(d) AS deleted
            FOREACH (d IN docs | DETACH DELETE d) RETURN deleted""",
            ids=list(ids),
            database_=self._database,
        )
        return int(records[0]["deleted"]) if records else 0

    async def search(
        self,
        query: str,
        *,
        limit: int = 10,
        site: str | None = None,
    ) -> list[tuple[ContentDocument, float]]:
        vector = await embed_query(self._embedder, query)
        if await self._supports_search_clause():
            statement = f"""MATCH (d:NLWebDocument)
            SEARCH d IN (VECTOR INDEX {self._index} FOR $embedding LIMIT $limit)
            SCORE AS score
            WHERE $site IS NULL OR d.site = $site
            RETURN d.id AS id, d.url AS url, d.title AS title, d.content AS content,
                   d.schemaJson AS schema, d.site AS site, d.metadataJson AS metadata, score
            ORDER BY score DESC"""
            records, _, _ = await self._driver.execute_query(
                statement,
                limit=limit,
                embedding=[float(value) for value in vector],
                site=site,
                database_=self._database,
            )
        else:
            # Neo4j versions before 2026.01 do not provide SEARCH. Keep the
            # compatibility path for existing deployments; current Neo4j uses
            # SEARCH and therefore does not emit the deprecated-procedure warning.
            statement = """CALL db.index.vector.queryNodes($index, $limit, $embedding)
            YIELD node AS d, score
            WHERE $site IS NULL OR d.site = $site
            RETURN d.id AS id, d.url AS url, d.title AS title, d.content AS content,
                   d.schemaJson AS schema, d.site AS site, d.metadataJson AS metadata, score
            ORDER BY score DESC"""
            records, _, _ = await self._driver.execute_query(
                statement,
                index=self._index,
                limit=limit,
                embedding=[float(value) for value in vector],
                site=site,
                database_=self._database,
            )
        return [_record_to_match(record) for record in records]

    async def _supports_search_clause(self) -> bool:
        records, _, _ = await self._driver.execute_query(
            "CALL dbms.components() YIELD versions RETURN versions[0] AS version",
            database_=self._database,
        )
        if not records:
            return False
        raw = str(records[0]["version"])
        parts = raw.split(".")
        try:
            major, minor = int(parts[0]), int(parts[1])
        except (ValueError, IndexError):
            return False
        return major > 2026 or (major == 2026 and minor >= 1)

    async def health(self) -> dict[str, object]:
        await self._driver.verify_connectivity()
        return {
            "backend": "neo4j-knowledge-graph",
            "database": self._database,
            "status": "ok",
        }

    async def close(self) -> None:
        await self._driver.close()


def _record_to_match(record: Any) -> tuple[ContentDocument, float]:
    schema = record["schema"]
    metadata = record["metadata"]
    return (
        ContentDocument(
            id=record["id"],
            url=record["url"],
            title=record["title"],
            content=record["content"],
            schema_object=json.loads(schema)
            if isinstance(schema, str)
            else schema or {},
            site=record["site"],
            metadata=json.loads(metadata)
            if isinstance(metadata, str)
            else metadata or {},
        ),
        float(record["score"]),
    )


def _safe_identifier(value: str) -> str:
    if not value or not value.replace("_", "").isalnum() or value[0].isdigit():
        raise ValueError(
            "identifier must be alphanumeric/underscore and not start with a digit"
        )
    return value
