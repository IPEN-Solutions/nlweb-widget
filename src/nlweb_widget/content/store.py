import json
from collections.abc import Sequence
from typing import Any

from ..models import ContentDocument
from .retrieval import EmbeddingProvider, embed_query


class PgVectorStore:
    """Optional PostgreSQL + pgvector semantic retrieval provider."""

    def __init__(
        self,
        database_url: str,
        embedding_provider: EmbeddingProvider,
        *,
        dimensions: int = 1536,
        table: str = "nlweb_documents",
    ) -> None:
        try:
            from sqlalchemy.ext.asyncio import create_async_engine
        except ImportError as exc:
            raise RuntimeError(
                "PostgreSQL support requires the 'postgres' extra"
            ) from exc
        self._table = _safe_identifier(table)
        self._dimensions = dimensions
        self._embedder = embedding_provider
        self._engine = create_async_engine(database_url, pool_pre_ping=True)

    async def initialize(self) -> None:
        from sqlalchemy import text

        async with self._engine.begin() as connection:
            await connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            await connection.execute(
                text(
                    f"""CREATE TABLE IF NOT EXISTS {self._table} (
                    id TEXT PRIMARY KEY,
                    url TEXT NOT NULL,
                    title TEXT NOT NULL,
                    content TEXT NOT NULL,
                    schema_object JSONB NOT NULL DEFAULT '{{}}'::jsonb,
                    site TEXT NOT NULL DEFAULT 'default',
                    metadata JSONB NOT NULL DEFAULT '{{}}'::jsonb,
                    embedding vector({self._dimensions}) NOT NULL,
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
                )"""
                )
            )
            await connection.execute(
                text(
                    f"CREATE INDEX IF NOT EXISTS {self._table}_embedding_hnsw "
                    f"ON {self._table} USING hnsw (embedding vector_cosine_ops)"
                )
            )

    async def upsert(
        self, documents: Sequence[ContentDocument] | ContentDocument
    ) -> int:
        from sqlalchemy import text

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
        statement = text(
            f"""INSERT INTO {self._table}
            (id,url,title,content,schema_object,site,metadata,embedding,updated_at)
            VALUES (:id,:url,:title,:content,CAST(:schema_object AS jsonb),:site,
                    CAST(:metadata AS jsonb),CAST(:embedding AS vector),now())
            ON CONFLICT(id) DO UPDATE SET
              url=EXCLUDED.url,title=EXCLUDED.title,content=EXCLUDED.content,
              schema_object=EXCLUDED.schema_object,site=EXCLUDED.site,
              metadata=EXCLUDED.metadata,embedding=EXCLUDED.embedding,updated_at=now()"""
        )
        async with self._engine.begin() as connection:
            for document, vector in zip(documents, vectors, strict=True):
                await connection.execute(
                    statement,
                    {
                        "id": document.id,
                        "url": str(document.url),
                        "title": document.title,
                        "content": document.content,
                        "schema_object": json.dumps(
                            document.schema_object, ensure_ascii=False
                        ),
                        "site": document.site or "default",
                        "metadata": json.dumps(
                            document.metadata, ensure_ascii=False, default=str
                        ),
                        "embedding": _vector(vector),
                    },
                )
        return len(documents)

    async def delete(self, ids: Sequence[str]) -> int:
        if not ids:
            return 0
        from sqlalchemy import text

        async with self._engine.begin() as connection:
            result = await connection.execute(
                text(f"DELETE FROM {self._table} WHERE id = ANY(:ids)"),
                {"ids": list(ids)},
            )
        return int(result.rowcount or 0)

    async def search(
        self,
        query: str,
        *,
        limit: int = 10,
        site: str | None = None,
    ) -> list[tuple[ContentDocument, float]]:
        from sqlalchemy import text

        vector = await embed_query(self._embedder, query)
        site_filter = " AND site = :site" if site else ""
        statement = text(
            f"""SELECT id,url,title,content,schema_object,site,metadata,
            1-(embedding <=> CAST(:embedding AS vector)) AS score
            FROM {self._table} WHERE true{site_filter}
            ORDER BY embedding <=> CAST(:embedding AS vector) LIMIT :limit"""
        )
        params: dict[str, Any] = {"embedding": _vector(vector), "limit": limit}
        if site:
            params["site"] = site
        async with self._engine.connect() as connection:
            rows = await connection.execute(statement, params)
        return [_row_to_match(row._mapping) for row in rows]

    async def health(self) -> dict[str, object]:
        from sqlalchemy import text

        async with self._engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
        return {"backend": "postgresql+pgvector", "table": self._table, "status": "ok"}

    async def close(self) -> None:
        await self._engine.dispose()


def _row_to_match(row: Any) -> tuple[ContentDocument, float]:
    schema_object = row["schema_object"]
    metadata = row["metadata"]
    if isinstance(schema_object, str):
        schema_object = json.loads(schema_object)
    if isinstance(metadata, str):
        metadata = json.loads(metadata)
    return (
        ContentDocument(
            id=row["id"],
            url=row["url"],
            title=row["title"],
            content=row["content"],
            schema_object=schema_object or {},
            site=row["site"],
            metadata=metadata or {},
        ),
        float(row["score"]),
    )


def _vector(values: Sequence[float]) -> str:
    return "[" + ",".join(str(float(value)) for value in values) + "]"


def _safe_identifier(value: str) -> str:
    if not value or not value.replace("_", "").isalnum() or value[0].isdigit():
        raise ValueError("table must be a simple SQL identifier")
    return value
