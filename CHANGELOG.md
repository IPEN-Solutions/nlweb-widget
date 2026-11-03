# Changelog

## 0.9.12 (approved immutable release)

- Approved after consumer-side Windows/Python 3.10.21 QA: 58 passed, 6 optional-provider tests skipped.
- HTTP `/ask` streaming emits SSE `start`, indexed `result`, optional `error`, and `complete` events when `prefer.streaming` is true, including the textual value `"true"`.
- The MCP JSON-RPC binding remains separate from HTTP SSE streaming.

## 0.9.12-r2 candidate (historical local QA)

- Added NLWeb v0.55 SSE streaming events (`start`, indexed `result`, optional `error`, and `complete`) for `/ask` in FastAPI, Starlette, Flask, and the stdlib HTTP integration.
- Preserved non-streaming JSON behavior and interpreted textual `streaming: false` correctly.
- Added streaming conformance tests for event ordering, result payloads, and session context.


- Make `summarize` a result-stream item (`@type: SearchSummary`, `text`) instead of a top-level `summary` replacement.
- Treat a comma-separated mode preference containing `summarize` as a request to include a summary item.
- Project authoritative JSON-LD entity properties into result items rather than exposing a nested `schema_object` implementation wrapper.
- Preserve grounding metadata through `/ask` and MCP tool structured content.
- Add regression coverage for typed summaries, graph-backed primary entities, and grounding preservation.
- Candidate only; the immutable 0.9.11 archive remains unchanged.

## 0.9.11

- Completed release documentation, agent-governance artifacts, and secure CI/CD/PyPI publishing guidance without changing runtime implementation.
- Added a credential-classification template and explicit secret exclusion rules for agentic coding.

## 0.9.11-r2 candidate-local-qa-r6

- Fixed the packaging omission for the existing optional SQLite + sqlite-vec provider by declaring `sqlite-vec==0.1.8` in the `sqlite` optional dependency extra.
- Kept the SQLite provider implementation, public retrieval contract, configuration surface, and pinned version unchanged.
- This corrective round exists so a clean consumer environment can install `nlweb-widget[sqlite]` and execute the explicitly configured SQLite provider test instead of being skipped for a missing runtime dependency.

## 0.9.11-r2 corrective candidate-local-qa-r5

- Added SQLite + sqlite-vec as an additive optional retrieval provider using SQLite FTS5 plus vector KNN behind the existing retrieval boundary.
- Pinned the optional sqlite-vec dependency to `0.1.8` and kept database path/vector dimensions configuration-driven.
- Hardened Qdrant Edge test isolation so configured provider tests use isolated temporary state and the framework-neutral `/ask` smoke uses the injected store without conflicting provider settings.
- Changed provider-boundary retrieval failures to structured `RetrievalError` messages rather than blind protocol-level exception handling.
- Kept the optional Docling adapter backward-compatible while making its safe-PDF dependency imports lazy, so the existing unit test contract remains independent of Docling internals.

# Changelog

## 0.9.11-r2 candidate-local-qa-r3

- Qdrant Server configured tests now perform initialize/upsert/search/cleanup against the configured service.
- Qdrant Edge reuses its open shard instead of reopening the WAL during repeated operations.
- FastAPI `/ask` and `/mcp` retain the established HTTP/error contract while exposing rich editable OpenAPI request schemas.
- Optional Docling execution uses the current markdown export API; provider examples document CPU/low-thread local-QA controls.


## 0.9.11-r2 local-QA corrective round

- Added Qdrant Edge settings to `.env.example` and conditional configured-provider coverage.
- Included Qdrant Edge in the widget startup lifecycle.
- Added conditional configured-provider coverage for PostgreSQL + pgvector and Neo4j.
- Expanded README into a compact consumer-facing setup/reference document.
- Separated revision effects into this changelog.


### QA corrective round

- Configured Qdrant Server tests now perform real initialize/upsert/search/cleanup and skip only when no endpoint is configured.
- Qdrant Edge reuses an already-open shard instead of reopening its WAL on every operation.
- FastAPI `/ask` and `/mcp` expose typed NLWeb/MCP request schemas and editable OpenAPI examples.
- Provider VS Code tasks and launch configurations use a consistent `Provider: <backend> — <action>` convention.
- OpenRouter synthesis remains optional; retrieval query demos do not fail solely because optional answer synthesis is unavailable.
