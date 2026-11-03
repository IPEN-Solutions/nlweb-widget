from collections.abc import Sequence
from typing import Protocol

from .models import ContentDocument


class RetrievalStore(Protocol):
    async def upsert(self, document: ContentDocument) -> None: ...

    async def search(
        self,
        query: str,
        *,
        limit: int = 10,
        site: str | None = None,
    ) -> list[tuple[ContentDocument, float]]: ...


class MemoryRetrievalStore:
    """Dependency-free retrieval store for local use and tests."""

    def __init__(self) -> None:
        self.items: dict[str, ContentDocument] = {}

    async def upsert(self, document: ContentDocument) -> None:
        self.items[document.id] = document

    async def upsert_many(self, documents: Sequence[ContentDocument]) -> int:
        for document in documents:
            await self.upsert(document)
        return len(documents)

    async def search(
        self,
        query: str,
        *,
        limit: int = 10,
        site: str | None = None,
    ) -> list[tuple[ContentDocument, float]]:
        terms = {term for term in query.lower().split() if term}
        ranked: list[tuple[ContentDocument, float]] = []
        for document in self.items.values():
            if site and document.site != site:
                continue
            haystack = f"{document.title} {document.content}".lower()
            hits = sum(term in haystack for term in terms)
            if hits:
                ranked.append((document, hits / max(len(terms), 1)))
        ranked.sort(key=lambda item: item[1], reverse=True)
        return ranked[:limit]
