import pytest

from nlweb_widget.embedding_benchmark import benchmark_retrieval


class FakeProvider:
    async def embed(self, texts):
        return [[1.0, 0.0] if "alpha" in text else [0.0, 1.0] for text in texts]

    async def embed_query(self, texts):
        return await self.embed(texts)


@pytest.mark.asyncio
async def test_embedding_benchmark_reports_recall_and_dimensions() -> None:
    result = await benchmark_retrieval(
        FakeProvider(),
        ["alpha query", "beta query"],
        ["a", "b"],
        [("a", "alpha document"), ("b", "beta document")],
    )
    assert result.recall_at_1 == 1.0
    assert result.recall_at_3 == 1.0
    assert result.recall_at_5 == 1.0
    assert result.dimensions == 2
    assert result.mean_latency_ms >= 0
