# nlweb-widget

> **Approved immutable release:** `nlweb-widget 0.9.12`, promoted after consumer-reported Windows/Python 3.10.21 QA (58 passed, 6 skipped). The immutable 0.9.11 archive remains preserved as the previous baseline.

Framework-neutral Python widget for exposing authoritative domain data through the NLWeb protocol. The [official NLWeb Specification](https://nlweb.ai/docs/specification) is authoritative for wire-level behavior; example-specific ingestion conventions do not override it.

## Quick start

```powershell
uv add nlweb-widget
```

```python
from nlweb_widget import ContentDocument, NLWebWidget

widget = NLWebWidget(domain="https://example.com")
await widget.startup()
await widget.index(ContentDocument(
    id="service-1",
    url="https://example.com/services/ai",
    title="AI consulting",
    content="AI transformation and implementation services.",
    schema_object={"@type": "Service", "name": "AI consulting"},
))
```

The memory provider is dependency-free and remains the default. The widget is disabled by default until `NLWEB_ENABLED=true` is configured.

## HTTP integration

```python
from nlweb_widget.integrations.fastapi_integration import mount_fastapi_nlweb
mount_fastapi_nlweb(app, widget)
```

The same core works with the supported Flask, Django, Starlette, and standard-library adapters. Mounted protocol surfaces include `/ask`, `/mcp`, `/.well-known/nlweb`, and `/health`.

## Protocol request

`POST /ask` accepts the NLWeb sections `query`, `context`, `prefer`, and `meta`.

```json
{
  "query": {"text": "Which AI services do you provide?", "site": "default"},
  "context": {},
  "prefer": {"mode": "list", "response_format": "conversational_search"},
  "meta": {"version": "0.55", "session_context": {}}
}
```

Supported modes are `list` and `summarize`; supported response formats are `conversational_search` and `chatgpt_app`. Unsupported modes/formats produce explicit NLWeb failures. MCP independently exposes `tools/list` and `tools/call`, including structured content, `_meta`, `isError`, and JSON-RPC protocol errors.

For HTTP `/ask`, set `prefer.streaming` to `true` to request Server-Sent Events (`text/event-stream`). The implementation emits the specification event sequence `start`, indexed `result` events, an optional application-level `error`, and `complete` (including `session_context` when present). Set `prefer.streaming` to `false` or omit it for a single JSON response. The FastAPI, Starlette, Django, Flask, and standard-library HTTP adapters expose the streaming binding; the MCP tool-call response remains a separate binding.

## Retrieval providers

Install only the capability you need:

```powershell
uv sync --extra postgres
uv sync --extra neo4j
uv sync --extra haystack
uv sync --extra qdrant
uv sync --extra qdrant-edge
uv sync --extra sqlite
```

Configure the provider with `NLWEB_RETRIEVAL_STORE` and its corresponding `NLWEB_*` settings. Provider-specific validation is conditional.

### Qdrant Edge

```text
NLWEB_RETRIEVAL_STORE=qdrant_edge
NLWEB_QDRANT_EDGE_PATH=./.nlweb-qdrant-edge
NLWEB_QDRANT_EDGE_DIMENSIONS=1536
```

Qdrant Edge is an embedded/local provider and deliberately has a separate lifecycle from Qdrant Server/Cloud.

### SQLite + sqlite-vec

Install the optional provider with `nlweb-widget[sqlite]`. The package pins `sqlite-vec==0.1.8` for this candidate because the upstream extension remains pre-v1.


```text
NLWEB_RETRIEVAL_STORE=sqlite
NLWEB_SQLITE_PATH=./.nlweb-sqlite/nlweb.db
NLWEB_SQLITE_DIMENSIONS=384
```

The optional SQLite provider combines SQLite FTS5 keyword retrieval with
`sqlite-vec` KNN vector retrieval behind the same `RetrievalProvider` contract.
The extension is pinned to `sqlite-vec==0.1.8` because the upstream project
remains pre-v1 and explicitly warns that breaking changes may occur. The provider
keeps its database path and embedding dimensions configuration-driven.

### PostgreSQL + pgvector

```text
NLWEB_RETRIEVAL_STORE=pgvector
NLWEB_POSTGRES_DATABASE_URL=postgresql+asyncpg://nlweb:nlweb@localhost:5432/nlweb
NLWEB_PGVECTOR_DIMENSIONS=1536
```

### Neo4j

```text
NLWEB_RETRIEVAL_STORE=neo4j
NLWEB_NEO4J_URI=neo4j://localhost:7687
NLWEB_NEO4J_USERNAME=neo4j
NLWEB_NEO4J_PASSWORD=...
NLWEB_NEO4J_VECTOR_DIMENSIONS=1536
```

Neo4j vector dimensions are configuration-driven. The provider uses `SEARCH` on supported versions and retains an explicit legacy fallback.

## Embeddings and document ingestion

Install multilingual local embeddings with `uv sync --extra embeddings`. E5-family models receive `query:`/`passage:` prefixes automatically unless overridden. Applications can inject their own embedding provider.

Install Docling with `uv sync --extra documents` to normalize supported unstructured sources into `ContentDocument`. Parser-specific objects never cross the public boundary.

The dependency-free `nlweb_widget.embedding_benchmark` harness reports Recall@1/3/5, mean query latency, and dimensions for provider/model selection.

## Configuration

The project-root `.env` is the minimum startup configuration source. `.env.example` contains commented optional-provider settings, including Qdrant Edge.

## Development and QA

```powershell
uv sync --dev
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv build
```

Optional-provider integration tests skip when the provider is not explicitly configured and fail when a configured provider cannot be exercised.

## Release governance

This release is governed by `revision-iteration-manifest-0.9.12.toml`. Historical candidate manifests are retained as provenance; the approved release record is authoritative for 0.9.12 status.

See `CHANGELOG.md`, `MUTATION.md`, and `docs-provider-evaluations.md` for revision and provider details.


### QA corrective round

- Configured Qdrant Server tests now perform real initialize/upsert/search/cleanup and skip only when no endpoint is configured.
- Qdrant Edge reuses an already-open shard instead of reopening its WAL on every operation.
- FastAPI `/ask` and `/mcp` expose typed NLWeb/MCP request schemas and editable OpenAPI examples.
- Provider VS Code tasks and launch configurations use a consistent `Provider: <backend> — <action>` convention.
- OpenRouter synthesis remains optional; retrieval query demos do not fail solely because optional answer synthesis is unavailable.


### Optional Docling CPU-safe PDF mode

When the `documents` extra is enabled, `DOCLING_DEVICE`, `DOCLING_NUM_THREADS`, and `DOCLING_SAFE_PDF` control the optional document adapter. `DOCLING_SAFE_PDF=true` selects backend PDF text extraction without OCR/table/layout inference, avoiding unnecessary Torch/RT-DETR execution on constrained CPU hosts. The default remains `false` for backward-compatible Docling behavior; provider examples explicitly enable safe PDF mode for Windows local QA.


## Mutation review records

See `AUTHORITATIVE-DOMAIN-DATA-CONTRACT.md`, `CONTRACT-TRACEABILITY.md`, and `CONFLICTS-AND-LIMITATIONS.md` for the shared contract, requirement-to-test mapping, and unresolved promotion blockers.
