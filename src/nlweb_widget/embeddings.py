from collections.abc import Sequence
from typing import Any


class SentenceTransformersEmbeddingProvider:
    """Local sentence-transformers embedding provider.

    The model is loaded lazily. E5-style models automatically receive the
    recommended ``query:`` and ``passage:`` prefixes; other models are passed
    their text unchanged unless explicit prefixes are configured.
    """

    def __init__(
        self,
        model_name: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
        *,
        query_prefix: str | None = None,
        document_prefix: str | None = None,
        device: str | None = None,
        encode_kwargs: dict[str, Any] | None = None,
    ) -> None:
        self.model_name = model_name
        self.query_prefix = query_prefix
        self.document_prefix = document_prefix
        self.device = device
        self.encode_kwargs = encode_kwargs or {}
        self._model: Any | None = None

    def _load(self) -> Any:
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer
            except ImportError as exc:
                raise RuntimeError("Sentence Transformers support requires the 'embeddings' extra") from exc
            kwargs = {"device": self.device} if self.device else {}
            self._model = SentenceTransformer(self.model_name, **kwargs)
        return self._model

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        import asyncio
        return await asyncio.to_thread(self._encode, list(texts), False)

    async def embed_query(self, texts: Sequence[str]) -> list[list[float]]:
        import asyncio
        return await asyncio.to_thread(self._encode, list(texts), True)

    def _encode(self, texts: list[str], query: bool) -> list[list[float]]:
        prefix = self.query_prefix if query else self.document_prefix
        if prefix is None and "e5" in self.model_name.lower():
            prefix = "query: " if query else "passage: "
        prepared = [f"{prefix}{text}" if prefix else text for text in texts]
        vectors = self._load().encode(prepared, **self.encode_kwargs)
        return [list(map(float, vector)) for vector in vectors]

    @property
    def dimensions(self) -> int:
        return int(self._load().get_sentence_embedding_dimension())
