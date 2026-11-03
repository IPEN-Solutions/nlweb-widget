"""Small, dependency-free benchmark harness for comparing embedding providers."""

from dataclasses import dataclass
from time import perf_counter
from typing import Any


@dataclass(frozen=True)
class EmbeddingBenchmarkResult:
    recall_at_1: float
    recall_at_3: float
    recall_at_5: float
    mean_latency_ms: float
    dimensions: int | None


async def benchmark_retrieval(
    provider: Any,
    queries: list[str],
    relevant_ids: list[str],
    corpus: list[tuple[str, str]],
) -> EmbeddingBenchmarkResult:
    """Benchmark query-to-corpus retrieval for model/provider selection.

    ``relevant_ids[i]`` is the expected relevant corpus id for ``queries[i]``.
    The harness intentionally measures the provider abstraction rather than a
    concrete model library, keeping benchmark selection outside runtime code.
    """
    if len(queries) != len(relevant_ids):
        raise ValueError("queries and relevant_ids must have equal length")
    if not queries:
        raise ValueError("at least one query is required")

    documents = [text for _, text in corpus]
    document_ids = [identifier for identifier, _ in corpus]
    document_vectors = await provider.embed(documents)
    dimensions = len(document_vectors[0]) if document_vectors else None
    latencies: list[float] = []
    ranks: list[int | None] = []

    for query, expected in zip(queries, relevant_ids, strict=True):
        started = perf_counter()
        query_vectors = (
            await provider.embed_query([query])
            if hasattr(provider, "embed_query")
            else await provider.embed([query])
        )
        query_vector = query_vectors[0]
        scores = [
            (_cosine(query_vector, vector), identifier)
            for identifier, vector in zip(document_ids, document_vectors, strict=True)
        ]
        scores.sort(reverse=True)
        latencies.append((perf_counter() - started) * 1000)
        ranks.append(
            next(
                (index + 1 for index, (_, identifier) in enumerate(scores) if identifier == expected),
                None,
            )
        )

    def recall(k: int) -> float:
        return sum(rank is not None and rank <= k for rank in ranks) / len(ranks)

    return EmbeddingBenchmarkResult(
        recall_at_1=recall(1),
        recall_at_3=recall(3),
        recall_at_5=recall(5),
        mean_latency_ms=sum(latencies) / len(latencies),
        dimensions=dimensions,
    )


def _cosine(left: list[float], right: list[float]) -> float:
    if len(left) != len(right):
        raise ValueError("embedding dimensions do not match")
    dot = sum(a * b for a, b in zip(left, right, strict=True))
    left_norm = sum(value * value for value in left) ** 0.5
    right_norm = sum(value * value for value in right) ** 0.5
    if not left_norm or not right_norm:
        return 0.0
    return dot / (left_norm * right_norm)
