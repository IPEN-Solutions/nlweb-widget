import pytest

from nlweb_widget.embeddings import SentenceTransformersEmbeddingProvider


@pytest.mark.asyncio
async def test_e5_query_and_passage_prefixes_are_distinct() -> None:
    provider = SentenceTransformersEmbeddingProvider("intfloat/multilingual-e5-small")
    captured: list[str] = []

    class FakeModel:
        def encode(self, texts, **kwargs):
            captured.extend(texts)
            return [[1.0] for _ in texts]

        def get_sentence_embedding_dimension(self):
            return 1

    provider._model = FakeModel()
    await provider.embed(["document"])
    await provider.embed_query(["query"])
    assert captured == ["passage: document", "query: query"]
