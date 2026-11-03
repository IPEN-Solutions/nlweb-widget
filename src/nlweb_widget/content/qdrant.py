import asyncio
from collections.abc import Sequence
from typing import Any

from ..models import ContentDocument
from .retrieval import EmbeddingProvider, embed_query


class QdrantRetrievalStore:
    """Optional Qdrant Server/Cloud semantic retrieval provider.

    Only the official Qdrant client is used behind the widget's own provider
    abstraction. The public API therefore does not expose Qdrant internals.
    """

    def __init__(
        self,
        url: str,
        embedding_provider: EmbeddingProvider,
        *,
        collection: str = "nlweb_documents",
        dimensions: int = 1536,
        api_key: str | None = None,
    ) -> None:
        try:
            from qdrant_client import QdrantClient
        except ImportError as exc:
            raise RuntimeError("Qdrant support requires the 'qdrant' extra") from exc
        self._client = QdrantClient(url=url, api_key=api_key)
        self._models = __import__("qdrant_client.models", fromlist=["models"])
        self._embedder = embedding_provider
        self._collection = _safe_identifier(collection)
        self._dimensions = dimensions

    async def initialize(self) -> None:
        def create() -> None:
            if not self._client.collection_exists(self._collection):
                self._client.create_collection(
                    collection_name=self._collection,
                    vectors_config=self._models.VectorParams(
                        size=self._dimensions,
                        distance=self._models.Distance.COSINE,
                    ),
                )
        await asyncio.to_thread(create)

    async def upsert(self, documents: Sequence[ContentDocument] | ContentDocument) -> int:
        items = [documents] if isinstance(documents, ContentDocument) else list(documents)
        vectors = await self._embedder.embed([document.content for document in items])
        points = [
            self._models.PointStruct(
                id=document.id,
                vector=vector,
                payload={
                    "url": str(document.url),
                    "title": document.title,
                    "content": document.content,
                    "schema_object": document.schema_object,
                    "site": document.site or "default",
                    "metadata": document.metadata,
                },
            )
            for document, vector in zip(items, vectors, strict=True)
        ]
        await asyncio.to_thread(
            self._client.upsert,
            collection_name=self._collection,
            points=points,
            wait=True,
        )
        return len(items)

    async def delete(self, ids: Sequence[str]) -> int:
        if not ids:
            return 0
        await asyncio.to_thread(
            self._client.delete,
            collection_name=self._collection,
            points_selector=self._models.PointIdsList(points=list(ids)),
            wait=True,
        )
        return len(ids)

    async def search(
        self,
        query: str,
        *,
        limit: int = 10,
        site: str | None = None,
    ) -> list[tuple[ContentDocument, float]]:
        vector = await embed_query(self._embedder, query)
        query_filter = None
        if site:
            query_filter = self._models.Filter(
                must=[self._models.FieldCondition(key="site", match=self._models.MatchValue(value=site))]
            )

        def search_points() -> Any:
            if hasattr(self._client, "query_points"):
                return self._client.query_points(
                    collection_name=self._collection,
                    query=vector,
                    query_filter=query_filter,
                    limit=limit,
                ).points
            return self._client.search(
                collection_name=self._collection,
                query_vector=vector,
                query_filter=query_filter,
                limit=limit,
            )

        points = await asyncio.to_thread(search_points)
        return [_point_to_match(point) for point in points]

    async def health(self) -> dict[str, object]:
        await asyncio.to_thread(self._client.get_collections)
        return {"backend": "qdrant", "collection": self._collection, "status": "ok"}

    async def close(self) -> None:
        close = getattr(self._client, "close", None)
        if close is not None:
            await asyncio.to_thread(close)


def _point_to_match(point: Any) -> tuple[ContentDocument, float]:
    payload = point.payload or {}
    return (
        ContentDocument(
            id=str(point.id),
            url=payload.get("url", str(point.id)),
            title=payload.get("title", str(point.id)),
            content=payload.get("content", ""),
            schema_object=payload.get("schema_object", {}),
            site=payload.get("site"),
            metadata=payload.get("metadata", {}),
        ),
        float(point.score),
    )


def _safe_identifier(value: str) -> str:
    if not value or not value.replace("_", "").isalnum() or value[0].isdigit():
        raise ValueError("collection must be a simple identifier")
    return value
