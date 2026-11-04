from collections.abc import Sequence
from typing import Any

from ..models import ContentDocument
from .retrieval import EmbeddingProvider, embed_query


class HaystackInMemoryRetrievalStore:
    """Optional Haystack-backed in-memory semantic retrieval provider.

    Haystack remains behind this package's RetrievalProvider boundary so callers
    do not depend on Haystack internals. The injected embedding provider owns
    model selection and vector generation.
    """

    def __init__(self, embedding_provider: EmbeddingProvider) -> None:
        try:
            from haystack import Document
            from haystack.components.retrievers.in_memory import (
                InMemoryEmbeddingRetriever,
            )
            from haystack.document_stores.in_memory import InMemoryDocumentStore
        except ImportError as exc:
            raise RuntimeError(
                "Haystack support requires the 'haystack' extra"
            ) from exc
        self._Document = Document
        self._store = InMemoryDocumentStore(embedding_similarity_function="cosine")
        self._retriever = InMemoryEmbeddingRetriever(self._store)
        self._embedder = embedding_provider

    async def initialize(self) -> None:
        return None

    async def upsert(
        self, documents: Sequence[ContentDocument] | ContentDocument
    ) -> int:
        items = (
            [documents] if isinstance(documents, ContentDocument) else list(documents)
        )
        vectors = await self._embedder.embed([document.content for document in items])
        haystack_documents = [
            self._Document(
                id=document.id,
                content=document.content,
                embedding=vector,
                meta={
                    "url": str(document.url),
                    "title": document.title,
                    "site": document.site or "default",
                    "schema_object": document.schema_object,
                    "metadata": document.metadata,
                },
            )
            for document, vector in zip(items, vectors, strict=True)
        ]
        self._store.write_documents(haystack_documents)
        return len(items)

    async def delete(self, ids: Sequence[str]) -> int:
        existing = [
            item.id
            for item in self._store.filter_documents(
                {"field": "id", "operator": "in", "value": list(ids)}
            )
        ]
        if existing:
            self._store.delete_documents(existing)
        return len(existing)

    async def search(
        self,
        query: str,
        *,
        limit: int = 10,
        site: str | None = None,
    ) -> list[tuple[ContentDocument, float]]:
        vector = await embed_query(self._embedder, query)
        filters: dict[str, Any] | None = None
        if site:
            filters = {"field": "meta.site", "operator": "==", "value": site}
        result = self._retriever.run(
            query_embedding=vector, top_k=limit, filters=filters
        )
        return [
            (
                ContentDocument(
                    id=document.id,
                    url=document.meta.get("url", document.id),
                    title=document.meta.get("title", document.id),
                    content=document.content or "",
                    schema_object=document.meta.get("schema_object", {}),
                    site=document.meta.get("site"),
                    metadata=document.meta.get("metadata", {}),
                ),
                float(document.score or 0.0),
            )
            for document in result["documents"]
        ]

    async def health(self) -> dict[str, object]:
        return {"backend": "haystack-inmemory", "status": "ok"}

    async def close(self) -> None:
        return None
