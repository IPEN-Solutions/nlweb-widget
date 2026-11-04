from collections.abc import Sequence
from typing import Protocol

from ..models import ContentDocument


class EmbeddingProvider(Protocol):
    async def embed(self, texts: Sequence[str]) -> list[list[float]]: ...


class RetrievalProvider(Protocol):
    async def upsert(self, documents: Sequence[ContentDocument]) -> int: ...
    async def delete(self, ids: Sequence[str]) -> int: ...
    async def search(
        self,
        query: str,
        *,
        limit: int = 10,
        site: str | None = None,
    ) -> list[tuple[ContentDocument, float]]: ...
    async def health(self) -> dict[str, object]: ...
    async def close(self) -> None: ...


async def embed_query(provider: EmbeddingProvider, query: str) -> list[float]:
    """Embed a search query, honoring providers that distinguish query/passage text."""
    method = getattr(provider, "embed_query", None)
    vectors = (
        await method([query]) if method is not None else await provider.embed([query])
    )
    return vectors[0]
