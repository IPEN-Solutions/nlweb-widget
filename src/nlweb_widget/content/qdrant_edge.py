import asyncio
from collections.abc import Sequence
from pathlib import Path
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

from ..errors import OptionalDependencyError, ProviderInitializationError, RetrievalError
from ..models import ContentDocument
from .retrieval import EmbeddingProvider, embed_query


class QdrantEdgeRetrievalStore:
    """Optional in-process Qdrant Edge retrieval provider.

    Qdrant Edge is deliberately separate from the Qdrant Server/Cloud provider:
    Edge is an embedded local shard with its own persistence lifecycle and does
    not require a network endpoint.
    """

    VECTOR_NAME = "nlweb"

    def __init__(
        self,
        path: str,
        embedding_provider: EmbeddingProvider,
        *,
        dimensions: int = 1536,
    ) -> None:
        try:
            from qdrant_edge import Distance, EdgeConfig, EdgeShard, EdgeVectorParams
        except ImportError as exc:
            raise OptionalDependencyError("Qdrant Edge support requires the 'qdrant-edge' extra") from exc
        self._embedding_provider = embedding_provider
        self._path = str(Path(path))
        self._dimensions = dimensions
        self._Distance = Distance
        self._EdgeConfig = EdgeConfig
        self._EdgeShard = EdgeShard
        self._EdgeVectorParams = EdgeVectorParams
        self._shard: Any | None = None

    async def initialize(self) -> None:
        await asyncio.to_thread(self._ensure_shard)

    def _ensure_shard(self) -> None:
        if self._shard is not None:
            return
        path = Path(self._path)
        path.mkdir(parents=True, exist_ok=True)
        has_persistent_state = path.exists() and any(path.iterdir())
        if has_persistent_state:
            try:
                self._shard = self._EdgeShard.load(self._path)
            except Exception as exc:
                raise ProviderInitializationError(
                    f"Qdrant Edge shard load failed for {self._path}: {exc}"
                ) from exc
            return
        config = self._EdgeConfig(
            vectors={
                self.VECTOR_NAME: self._EdgeVectorParams(
                    size=self._dimensions,
                    distance=self._Distance.Cosine,
                )
            }
        )
        try:
            self._shard = self._EdgeShard.create(self._path, config)
        except Exception as exc:
            raise ProviderInitializationError(
                f"Qdrant Edge shard creation failed for {self._path}: {exc}"
            ) from exc

    async def upsert(self, documents: Sequence[ContentDocument] | ContentDocument) -> int:
        items = [documents] if isinstance(documents, ContentDocument) else list(documents)
        if not items:
            return 0
        await self.initialize()
        vectors = await self._embedding_provider.embed([document.content for document in items])
        from qdrant_edge import Point, UpdateOperation

        points = [
            Point(
                id=_point_id(document.id),
                vector={self.VECTOR_NAME: vector},
                payload={
                    "document_id": document.id,
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
        try:
            await asyncio.to_thread(self._shard.update, UpdateOperation.upsert_points(points))
        except Exception as exc:
            raise RetrievalError(f"Qdrant Edge upsert failed for {len(items)} document(s): {exc}") from exc
        return len(items)

    async def delete(self, ids: Sequence[str]) -> int:
        if not ids:
            return 0
        await self.initialize()
        from qdrant_edge import UpdateOperation

        # qdrant-edge-py 0.8 exposes PointId as the scalar delete-point ID
        # contract; the older PointIds wrapper is not exported.
        point_ids = [_point_id(identifier) for identifier in ids]
        try:
            await asyncio.to_thread(
                self._shard.update,
                UpdateOperation.delete_points(point_ids),
            )
        except Exception as exc:
            raise RetrievalError(f"Qdrant Edge delete failed for {len(ids)} document(s): {exc}") from exc
        return len(ids)

    async def search(
        self,
        query: str,
        *,
        limit: int = 10,
        site: str | None = None,
    ) -> list[tuple[ContentDocument, float]]:
        await self.initialize()
        from qdrant_edge import Filter, FieldCondition, MatchValue, Query, QueryRequest

        vector = await embed_query(self._embedding_provider, query)
        query_filter = None
        if site:
            query_filter = Filter(
                must=[FieldCondition(key="site", match=MatchValue(value=site))]
            )
        request = QueryRequest(
            query=Query.Nearest(vector, using=self.VECTOR_NAME),
            filter=query_filter,
            limit=limit,
            with_vector=False,
            with_payload=True,
        )
        try:
            results = await asyncio.to_thread(self._shard.query, request)
        except Exception as exc:
            raise RetrievalError(f"Qdrant Edge search failed for query {query!r}: {exc}") from exc
        return [_edge_result_to_match(item) for item in results]

    async def health(self) -> dict[str, object]:
        await self.initialize()
        return {"backend": "qdrant-edge", "path": self._path, "status": "ok"}

    async def close(self) -> None:
        if self._shard is not None:
            await asyncio.to_thread(self._shard.close)
            self._shard = None


def _edge_result_to_match(item: Any) -> tuple[ContentDocument, float]:
    payload = getattr(item, "payload", None) or {}
    return (
        ContentDocument(
            id=str(payload.get("document_id", getattr(item, "id", ""))),
            url=payload.get("url", str(getattr(item, "id", ""))),
            title=payload.get("title", str(getattr(item, "id", ""))),
            content=payload.get("content", ""),
            schema_object=payload.get("schema_object", {}),
            site=payload.get("site"),
            metadata=payload.get("metadata", {}),
        ),
        float(getattr(item, "score", 0.0)),
    )

def _point_id(document_id: str) -> str:
    """Map arbitrary ContentDocument ids to Qdrant Edge's UUID point contract."""
    try:
        return str(UUID(document_id))
    except ValueError:
        return str(uuid5(NAMESPACE_URL, f"nlweb-widget:qdrant-edge:{document_id}"))

