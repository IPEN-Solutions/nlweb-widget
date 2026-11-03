# Architecture

`nlweb-widget` is deliberately split into stable protocol/core abstractions and optional provider implementations.

```text
web framework adapter
        |
        v
  NLWeb protocol core
        |
        +---- authoritative content ingestion
        |
        +---- RetrievalProvider boundary
                 |
                 +-- memory
                 +-- Haystack InMemory (optional)
                 +-- PostgreSQL + pgvector (optional)
                 +-- Neo4j (optional)
                 +-- Qdrant Server/Cloud (optional)
                 +-- Qdrant Edge (optional, separate in-process path)
```

## Compatibility boundary

The public `NLWebWidget`, request/response models, retrieval protocols, and framework adapters remain the stable consumer-facing surface. Provider libraries are implementation details behind those interfaces.

## Retrieval

All semantic providers receive an injected `EmbeddingProvider` or use the optional local sentence-transformers helper. This keeps model choice outside store implementation and prevents incompatible vector dimensions from being silently mixed.

## Neo4j

Schema and vector-index DDL remain explicit Cypher. On Neo4j 2026.01+ the store uses the `SEARCH` clause for vector retrieval; older supported servers use the legacy vector procedure as a compatibility path.

## Content ingestion

Structured Schema.org/JSON-LD, web-page JSON-LD, RSS/Atom, sitemap, database, and custom callable sources remain supported. `CUSTOM` additionally has an optional Docling-backed document adapter for common unstructured files. Optional parsing libraries are not part of the base runtime dependency set.

## Protocol compliance

The `/ask` core owns the complete NLWeb v0.55 request envelope (`query`, `context`, `prefer`, `meta`), applies site/domain filters, emits the `_meta` response envelope, and supports the two normative response formats additively. Streaming remains an explicit transport capability not claimed by this core; a complete response is returned with `_meta.streaming=false` when requested.

`/mcp` has an independent MCP binding contract. `tools/list` exposes only capabilities actually implemented by the widget, `tools/call` maps application failures to `isError=true`, and unknown tools/invalid JSON-RPC requests use MCP protocol errors. NLWeb reference implementation internals are never imported.
