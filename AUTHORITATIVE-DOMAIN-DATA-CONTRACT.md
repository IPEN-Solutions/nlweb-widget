# Shared NLWeb Widget authoritative domain data contract

Status: approved planning baseline; implementation candidates are pending local-QA approval. This document is shared by the Widget and Examples mutation iterations. Official wire behavior is governed by the [NLWeb Specification](https://nlweb.ai/docs/specification), currently reviewed at v0.55 for the SSE event contract.

## Authority and precedence

1. Applicable official NLWeb and MCP protocol requirements govern wire behavior.
2. The Widget owns correct protocol serialization and transport behavior. An Examples convention cannot force or justify a conflicting Widget behavior.
3. The approved source-data contract governs how examples identify artifacts and retain source metadata.
4. Consumer-selected manifests and optional metadata may extend behavior only when they do not override standardized field semantics or required response structures.

Any suspected conflict must be recorded with the conflicting requirements, affected boundary, evidence, and proposed resolution. It is not silently considered approved.

## Result serialization

- For conversational-search responses, a requested `summarize` mode produces a result item with `@type: "SearchSummary"` (or a justified domain-specific type) and `text` containing the summary.
- A top-level `summary` property must not substitute for that result item.
- If the mode preference includes `summarize` among multiple comma-separated modes, the Widget must include a summary item.
- Result objects should expose the relevant authoritative schema properties at the result level rather than a private implementation wrapper such as `schema_object`.
- A suitable source `@type` is preserved. A manifest-declared type is a fallback only when the structured source has no suitable type.
- Optional grounding metadata must not be used to replace or redefine protocol fields. Its allowed shape and placement must conform to the applicable official specification, not merely to the examples manifest.

## Artifact identity and URL precedence

- Artifact identity is independent from chunk identity. All chunks for one artifact share the same canonical artifact URL.
- Chunk uniqueness remains in document IDs and internal chunk metadata. Synthetic `#chunk-N` fragments must not be added.
- A suitable `url` wins over `@id` for the artifact URL when both are present. Preserve a distinct `@id` where it remains useful as schema identity.
- Converter-provided URLs are retained. Configured registry URL fallbacks are only used when suitable document/converter URLs are absent.
- A configured fallback that represents a base path receives the artifact filename. A filename alone never proves a public evidence URI exists.

## Optional inbox evidence manifest

The Examples candidate defines an optional version-1 `nlweb-evidence-manifest.json` control file. Each `artifacts[]` entry has a safe relative `artifact` key and may contain `type` and `grounding`.

- The manifest is not ingested as ordinary prose.
- Manifest type is a fallback only; suitable source type wins.
- Grounding supplied by the consumer is persisted as a complete JSON object unchanged at the metadata boundary. If source-schema and metadata grounding are both present and differ, the Widget reports a source-metadata failure instead of silently overwriting either value.
- Conflicting source and manifest grounding is an explicit ingestion error, not a silent overwrite.
- No manifest entry means no manifest-declared evidence URI. Other valid source grounding remains possible.
- A declared URI is a consumer assertion, not proof of public reachability or authenticity. Never expose private paths or fabricate public URLs.

## HTTP streaming contract

When `prefer.streaming` is true on HTTP `/ask`, the Widget must return `text/event-stream` using Server-Sent Events. The v0.55 specification defines `start` (with `_meta.streaming: true`), indexed `result` events whose `item` matches the non-streaming result-item shape, optional `error` events using the failure response structure, and one `complete` event. The completion `_meta` must preserve `session_context` when present. Non-streaming requests retain the single JSON response. Framework adapters must not claim streaming support unless they implement the actual SSE transport; MCP remains its own binding.

## Independent mutation ownership

Widget iteration owns `/ask`, response formats, result projection, summary item structure, grounding serialization, streaming transport, and MCP protocol behavior. Examples iteration owns URL normalization in example ingestion, optional manifest parsing, source type precedence, metadata persistence, sample data, and documentation. Both use the same contract revision but have independent candidates, QA records, hashes, and promotion gates.

## Known limits requiring explicit QA status

- This local sandbox has Python 3.13 but no Python 3.12 installation for the Examples project's declared environment; offline sync cannot provision it.
- Haystack is declared in the Examples dependencies but is not installed in this sandbox. The actual MultiFileConverter path therefore remains unverified here; installation was attempted but blocked by DNS/network unavailability.
- Streaming is implemented in the candidate, but only the FastAPI route has a direct end-to-end SSE test in this sandbox; the Starlette, Django, Flask, and stdlib adapters still require framework-specific conformance tests.
- Before promotion, the maintainer must confirm exact applicable NLWeb/MCP specification revisions for the supported release matrix and rerun QA in the supported clean environment.
