from collections.abc import Sequence
from typing import Any
from uuid import uuid4

from .content.models import ContentSource
from .content.service import ContentSyncService, load_content_sources
from .content.state import StateStore
from .errors import RetrievalError
from .models import ContentDocument, NLWebRequest, NLWebResponse, SearchResult
from .retrieval import MemoryRetrievalStore, RetrievalStore
from .settings import NLWebSettings, get_settings


class NLWebWidget:
    """Framework-neutral NLWeb core and authoritative-data projection facade."""

    def __init__(
        self,
        store: RetrievalStore | None = None,
        domain: str = "",
        *,
        settings: NLWebSettings | None = None,
        embedding_provider: Any | None = None,
        sync_service: ContentSyncService | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.store = store or self._build_store(embedding_provider)
        self.domain = domain.rstrip("/")
        self._sync_service = sync_service
        self._scheduler: Any | None = None
        self._sources: list[ContentSource] = []
        self._started = False

    @property
    def effective_state(self) -> str:
        """Return the widget-owned operational state used by protocol bindings."""
        return "enabled" if self.settings.enabled else "disabled"

    async def startup(self) -> None:
        """Initialize the provider and optionally project configured sources."""
        if self._started:
            return
        if not self.settings.enabled:
            return
        initialize = getattr(self.store, "initialize", None)
        should_initialize = (
            self.settings.retrieval_store == "pgvector" and self.settings.postgres_auto_initialize
        ) or (
            self.settings.retrieval_store == "neo4j" and self.settings.neo4j_auto_initialize
        ) or (
            self.settings.retrieval_store == "qdrant" and self.settings.qdrant_auto_initialize
        ) or (
            self.settings.retrieval_store == "qdrant_edge"
        )
        if initialize is not None and should_initialize:
            await initialize()
        self._started = True
        if not self.settings.content_sync_enabled:
            return
        self._sync_service = self._sync_service or ContentSyncService(
            state_store=StateStore(self.settings.content_sync_state_file),
            target=self.store,
        )
        self._sources = load_content_sources(self.settings.content_sources_file)
        if self.settings.content_sync_on_startup:
            await self.sync_sources(force=True)
        if self.settings.content_sync_interval_seconds > 0:
            from .content.scheduler import ContentSyncScheduler

            self._scheduler = ContentSyncScheduler(
                self.sync_sources,
                self.settings.content_sync_interval_seconds,
            )
            await self._scheduler.start()

    async def close(self) -> None:
        """Stop background synchronization and close the retrieval provider."""
        if self._scheduler is not None:
            await self._scheduler.stop()
            self._scheduler = None
        close = getattr(self.store, "close", None)
        if close is not None:
            await close()
        self._started = False

    async def sync_sources(self, *, force: bool = False) -> Any:
        """Synchronize the configured authoritative content sources."""
        if not self.settings.enabled:
            return None
        if self._sync_service is None:
            self._sync_service = ContentSyncService(
                state_store=StateStore(self.settings.content_sync_state_file),
                target=self.store,
            )
        if not self._sources:
            self._sources = load_content_sources(self.settings.content_sources_file)
        return await self._sync_service.sync_summary(self._sources, force=force)

    async def index(self, document: ContentDocument) -> None:
        """Project one authoritative document only while the widget is enabled."""
        if not self.settings.enabled:
            return
        await self.store.upsert(document)

    async def index_many(self, documents: Sequence[ContentDocument]) -> int:
        """Project multiple authoritative documents only while enabled."""
        if not self.settings.enabled:
            return 0
        if hasattr(self.store, "upsert_many"):
            return await self.store.upsert_many(documents)
        for document in documents:
            await self.store.upsert(document)
        return len(documents)

    async def ask(self, request: NLWebRequest) -> NLWebResponse:
        """Execute the framework-neutral NLWeb v0.55 ask operation."""
        query_id = str(uuid4())
        query_text = request.query.text.strip()
        if not query_text:
            return self._failure(query_id, request, "INVALID_QUERY", "query.text must not be empty")

        meta = request.meta or {}
        version = str(meta.get("version") or "0.55")
        if version != "0.55":
            return self._failure(
                query_id, request, "INVALID_QUERY", f"Unsupported NLWeb version: {version}"
            )

        prefer = request.prefer or {}
        requested_modes = {
            item.strip()
            for item in str(prefer.get("mode") or "list").split(",")
            if item.strip()
        }
        if not requested_modes:
            requested_modes = {"list"}
        unsupported_modes = requested_modes - {"list", "summarize"}
        if unsupported_modes:
            unsupported = ", ".join(sorted(unsupported_modes))
            return self._failure(
                query_id, request, "UNSUPPORTED_MODE", f"Unsupported mode: {unsupported}"
            )
        summarize_requested = "summarize" in requested_modes

        response_format = prefer.get("response_format") or prefer.get("format")
        if response_format and response_format not in {"conversational_search", "chatgpt_app"}:
            return self._failure(
                query_id, request, "UNSUPPORTED_FORMAT",
                f"Unsupported response format: {response_format}",
            )

        if not self.settings.enabled:
            return self._failure(query_id, request, "INTERNAL_ERROR", "NLWeb widget is disabled")

        try:
            matches = await self.store.search(query_text, site=request.query.site)
        except (RetrievalError, TypeError, ValueError, RuntimeError, OSError) as exc:
            return self._failure(query_id, request, "INTERNAL_ERROR", str(exc))

        filters = {
            key: value
            for key, value in request.query.model_extra.items()
            if key not in {"text", "site"}
        }
        if filters:
            matches = [
                (document, score)
                for document, score in matches
                if all(
                    _document_filter_matches(document, key, value)
                    for key, value in filters.items()
                )
            ]

        try:
            results = [
                SearchResult(
                    url=str(document.url),
                    name=document.title,
                    site=document.site or request.query.site,
                    score=score,
                    description=document.content,
                    schema_object=document.schema_object,
                    schema_type=_schema_type_for_document(document),
                    grounding=_grounding_for_document(document),
                )
                for document, score in matches
            ]
        except ValueError as exc:
            return self._failure(
                query_id, request, "INVALID_SOURCE_METADATA", str(exc)
            )
        if not results:
            return self._failure(query_id, request, "NO_RESULTS", "No matching results were found")

        summary_text = None
        if summarize_requested:
            summary_text = " ".join(
                (result.description or result.name or "").strip()
                for result in results[:3]
                if (result.description or result.name or "").strip()
            )[:2000]
            if not summary_text:
                summary_text = f"Found {len(results)} matching result(s) for: {query_text}"
            # NLWeb conversational-search summaries are result items. Do not
            # replace the results-stream item with a top-level `summary` field.
            results.insert(0, SearchResult(schema_type="SearchSummary", text=summary_text))

        response_meta: dict[str, Any] = {
            "version": version,
            "response_type": "answer",
            "response_format": response_format or "conversational_search",
        }
        session_context = meta.get("session_context")
        if isinstance(session_context, dict):
            response_meta["session_context"] = session_context
        if bool(prefer.get("streaming")):
            # Streaming is a transport capability. This core currently returns
            # the complete response; explicitly record that no stream was used.
            response_meta["streaming"] = False

        response = NLWebResponse(
            query_id=query_id,
            results=results,
            meta=response_meta,
        )
        if response_format == "chatgpt_app":
            structured = [_structured_result(result) for result in results if result.schema_type != "SearchSummary"]
            text = summary_text or " ".join(result.description or result.name or "" for result in results[:3])
            response.content = [{"type": "text", "text": text}]
            response.structured_data = structured
        return response

    @staticmethod
    def _failure(
        query_id: str, request: NLWebRequest, code: str, message: str
    ) -> NLWebResponse:
        meta = request.meta or {}
        version = str(meta.get("version") or "0.55")
        response_meta: dict[str, Any] = {"version": version, "response_type": "failure"}
        session_context = meta.get("session_context")
        if isinstance(session_context, dict):
            response_meta["session_context"] = session_context
        return NLWebResponse(
            query_id=query_id,
            meta=response_meta,
            error={"code": code, "message": message},
        )


    def discovery(self) -> dict[str, object]:
        return {
            "protocol": "NLWeb",
            "specification": "https://nlweb.ai/docs/specification",
            "endpoints": {"ask": "/ask", "mcp": "/mcp"},
            "discovery": "/.well-known/nlweb",
            "health": "/health",
            "operational_state": self.effective_state,
        }

    def _build_default_embedder(self) -> Any:
        from .embeddings import SentenceTransformersEmbeddingProvider
        return SentenceTransformersEmbeddingProvider(
            self.settings.embedding_model,
            query_prefix=self.settings.embedding_query_prefix,
            document_prefix=self.settings.embedding_document_prefix,
            device=self.settings.embedding_device,
        )

    def _build_store(self, embedding_provider: Any | None) -> RetrievalStore:
        selection = self.settings.retrieval_store
        if selection == "memory":
            return MemoryRetrievalStore()
        if selection in {"haystack", "haystack-memory"}:
            from .content.haystack import HaystackInMemoryRetrievalStore
            provider = embedding_provider or self._build_default_embedder()
            return HaystackInMemoryRetrievalStore(provider)
        if selection == "custom":
            raise ValueError("retrieval_store=custom requires an explicit store argument")
        embedding_provider = embedding_provider or self._build_default_embedder()
        if selection == "qdrant":
            from .content.qdrant import QdrantRetrievalStore
            return QdrantRetrievalStore(
                self.settings.qdrant_url or "",
                embedding_provider,
                collection=self.settings.qdrant_collection,
                dimensions=self.settings.qdrant_dimensions,
                api_key=self.settings.qdrant_api_key,
            )
        if selection == "qdrant_edge":
            from .content.qdrant_edge import QdrantEdgeRetrievalStore
            return QdrantEdgeRetrievalStore(
                self.settings.qdrant_edge_path,
                embedding_provider,
                dimensions=self.settings.qdrant_edge_dimensions,
            )
        if selection == "sqlite":
            from .content.sqlite import SQLiteVecRetrievalStore
            return SQLiteVecRetrievalStore(
                self.settings.sqlite_path,
                embedding_provider,
                dimensions=self.settings.sqlite_dimensions,
            )
        if selection == "pgvector":
            from .content.store import PgVectorStore

            return PgVectorStore(
                self.settings.postgres_database_url or "",
                embedding_provider,
                dimensions=self.settings.pgvector_dimensions,
                table=self.settings.pgvector_table,
            )
        from .content.neo4j import Neo4jKnowledgeGraphStore

        return Neo4jKnowledgeGraphStore(
            self.settings.neo4j_uri or "",
            self.settings.neo4j_username or "",
            self.settings.neo4j_password or "",
            embedding_provider,
            database=self.settings.neo4j_database,
            dimensions=self.settings.neo4j_vector_dimensions,
            vector_index=self.settings.neo4j_vector_index,
        )
def _grounding_for_document(document: ContentDocument) -> dict[str, Any] | None:
    metadata_grounding = document.metadata.get("grounding") if isinstance(document.metadata, dict) else None
    source_grounding = document.schema_object.get("grounding") if isinstance(document.schema_object, dict) else None
    if metadata_grounding is not None and not isinstance(metadata_grounding, dict):
        raise ValueError(f"Document {document.id!r} grounding metadata must be an object")
    if source_grounding is not None and not isinstance(source_grounding, dict):
        raise ValueError(f"Document {document.id!r} source grounding must be an object")
    if metadata_grounding is not None and source_grounding is not None and metadata_grounding != source_grounding:
        raise ValueError(f"Document {document.id!r} has conflicting source and metadata grounding; resolve explicitly")
    if metadata_grounding is not None:
        return metadata_grounding
    return source_grounding


def _schema_type_for_document(document: ContentDocument) -> str | None:
    schema = document.schema_object if isinstance(document.schema_object, dict) else {}
    if schema.get("@type"):
        return schema.get("@type")
    graph = schema.get("@graph")
    if isinstance(graph, list):
        for record in graph:
            if not isinstance(record, dict):
                continue
            if (record.get("url") == str(document.url) or record.get("@id") == str(document.url)) and record.get("@type"):
                return record["@type"]
        for record in graph:
            if isinstance(record, dict) and (record.get("name") == document.title or record.get("headline") == document.title) and record.get("@type"):
                return record["@type"]
        for record in graph:
            if isinstance(record, dict) and record.get("@type"):
                return record["@type"]
    return None


def _structured_result(result: SearchResult) -> dict[str, Any]:
    from .models import _project_schema_record

    base = _project_schema_record(result.schema_object, result.name, result.url)
    if result.schema_type and "@type" not in base:
        base["@type"] = result.schema_type
    base.setdefault("name", result.name)
    base.setdefault("description", result.description)
    if result.url:
        base.setdefault("url", result.url)
    if result.grounding is not None:
        base["grounding"] = result.grounding
    return base


def _document_filter_matches(document: ContentDocument, key: str, expected: Any) -> bool:
    """Apply schema.org/domain filters without changing the retrieval contract."""
    if hasattr(document, key):
        actual = getattr(document, key)
    elif key in document.schema_object:
        actual = document.schema_object[key]
    elif key in document.metadata:
        actual = document.metadata[key]
    else:
        return False
    if isinstance(expected, list):
        return any(_document_filter_matches_value(actual, item) for item in expected)
    return _document_filter_matches_value(actual, expected)


def _document_filter_matches_value(actual: Any, expected: Any) -> bool:
    if isinstance(actual, list):
        return expected in actual
    if isinstance(actual, dict) and isinstance(expected, dict):
        return all(actual.get(key) == value for key, value in expected.items())
    return actual == expected or str(actual).casefold() == str(expected).casefold()

