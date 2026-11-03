import asyncio
import random
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..errors import ContentSyncError
from .adapters import (
    CallableAdapter,
    ContentAdapter,
    DatabaseAdapter,
    DocumentAdapter,
    RSSAtomAdapter,
    SchemaJSONAdapter,
    SitemapAdapter,
    WebPageSchemaAdapter,
)
from .fingerprint import fingerprint_source
from .models import ContentSource, ContentSourceKind, SourceState, SyncResult, SyncSummary
from .state import StateStore

Loader = Callable[[ContentSource], Awaitable[Any] | Any]


class ContentSyncService:
    """Incrementally project authoritative sources into a retrieval provider."""

    def __init__(
        self,
        *,
        state_store: StateStore | None = None,
        target: Any | None = None,
        max_concurrency: int = 2,
        retries: int = 2,
        retry_backoff_seconds: float = 1.0,
        retry_jitter: float = 0.15,
        fingerprint_timeout_seconds: float = 15.0,
    ) -> None:
        self.state_store = state_store or StateStore(".nlweb-sync-state.json")
        self.target = target
        self.max_concurrency = max(1, max_concurrency)
        self.retries = max(0, retries)
        self.backoff = max(0.0, retry_backoff_seconds)
        self.jitter = max(0.0, retry_jitter)
        self.fingerprint_timeout = fingerprint_timeout_seconds
        self._adapters: dict[ContentSourceKind, ContentAdapter] = {
            ContentSourceKind.SCHEMA_JSON: SchemaJSONAdapter(),
            ContentSourceKind.WEBPAGE_SCHEMA: WebPageSchemaAdapter(),
            ContentSourceKind.RSS: RSSAtomAdapter(),
            ContentSourceKind.ATOM: RSSAtomAdapter(),
            ContentSourceKind.SITEMAP: SitemapAdapter(),
            ContentSourceKind.CUSTOM: DocumentAdapter(),
        }
        self._loaders: dict[ContentSourceKind, Loader] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    def register_adapter(self, kind: ContentSourceKind, adapter: ContentAdapter) -> None:
        self._adapters[kind] = adapter

    def register_loader(self, kind: ContentSourceKind, loader: Loader) -> None:
        self._loaders[kind] = loader

    async def sync(self, source: ContentSource, *, force: bool = False) -> SyncResult:
        lock = self._locks.setdefault(source.name, asyncio.Lock())
        async with lock:
            started = datetime.now(timezone.utc)
            previous = await self.state_store.get(source.name)
            fingerprint = None
            if source.kind not in self._loaders:
                fingerprint = await fingerprint_source(
                    source,
                    timeout=self.fingerprint_timeout,
                )
            if (
                not force
                and previous
                and fingerprint
                and previous.fingerprint == fingerprint
                and previous.last_status == "ok"
            ):
                return SyncResult(
                    source=source.name,
                    site=source.site,
                    kind=source.kind,
                    status="ok",
                    skipped=True,
                    message="Source fingerprint unchanged",
                    attempts=0,
                    started_at=started,
                    finished_at=datetime.now(timezone.utc),
                )

            last_error: Exception | None = None
            for attempt in range(1, self.retries + 2):
                try:
                    loaded = await self._execute(source)
                    item_keys = set(loaded.get("item_keys", []))
                    await self.state_store.put(
                        SourceState(
                            source=source.name,
                            fingerprint=fingerprint,
                            item_keys=item_keys,
                            last_success=datetime.now(timezone.utc),
                            last_attempt=datetime.now(timezone.utc),
                            last_status="ok",
                        )
                    )
                    return SyncResult(
                        source=source.name,
                        site=source.site,
                        kind=source.kind,
                        status="ok",
                        changed=True,
                        total_loaded=int(loaded.get("total_loaded", 0)),
                        deleted_count=int(loaded.get("deleted_count", 0)),
                        message=loaded.get("message"),
                        attempts=attempt,
                        started_at=started,
                        finished_at=datetime.now(timezone.utc),
                    )
                except ContentSyncError as exc:
                    last_error = exc
                    if attempt <= self.retries:
                        delay = self.backoff * (2 ** (attempt - 1))
                        if self.jitter:
                            delay += random.uniform(0, self.jitter * delay)
                        await asyncio.sleep(delay)
            await self.state_store.put(
                SourceState(
                    source=source.name,
                    fingerprint=previous.fingerprint if previous else fingerprint,
                    last_attempt=datetime.now(timezone.utc),
                    last_status="error",
                    last_error=str(last_error),
                )
            )
            return SyncResult(
                source=source.name,
                site=source.site,
                kind=source.kind,
                status="error",
                message=str(last_error),
                attempts=self.retries + 1,
                started_at=started,
                finished_at=datetime.now(timezone.utc),
            )

    async def sync_all(
        self, sources: list[ContentSource], *, force: bool = False
    ) -> list[SyncResult]:
        semaphore = asyncio.Semaphore(self.max_concurrency)

        async def run(source: ContentSource) -> SyncResult:
            async with semaphore:
                return await self.sync(source, force=force)

        return list(await asyncio.gather(*(run(source) for source in sources if source.enabled)))

    async def sync_summary(
        self, sources: list[ContentSource], *, force: bool = False
    ) -> SyncSummary:
        started = datetime.now(timezone.utc)
        results = await self.sync_all(sources, force=force)
        return SyncSummary(
            started_at=started,
            finished_at=datetime.now(timezone.utc),
            results=results,
        )

    async def _execute(self, source: ContentSource) -> dict[str, Any]:
        try:
            if source.kind in self._loaders:
                result = self._loaders[source.kind](source)
                result = await result if asyncio.iscoroutine(result) else result
                return dict(result)
            adapter = self._adapters.get(source.kind)
            if adapter is None:
                raise ValueError(f"No content adapter registered for {source.kind.value}")
            documents = await adapter.read(source)
            if self.target is None:
                return {
                    "total_loaded": len(documents),
                    "item_keys": [document.id for document in documents],
                    "documents": documents,
                    "message": "Parsed authoritative source; no retrieval target configured",
                }
            if hasattr(self.target, "upsert_many"):
                loaded = await self.target.upsert_many(documents)
            else:
                loaded = await self.target.upsert(documents)
            return {
                "total_loaded": loaded,
                "item_keys": [document.id for document in documents],
                "message": "Projected documents into configured retrieval store",
            }
        except ContentSyncError:
            raise
        except Exception as exc:
            raise ContentSyncError(
                f"Content source '{source.name}' ({source.kind.value}) execution failed: {exc}"
            ) from exc


__all__ = ["CallableAdapter", "ContentSyncService", "DatabaseAdapter"]


def load_content_sources(path: str | Path) -> list[ContentSource]:
    """Load widget-owned source definitions from a JSON configuration file."""
    import json

    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        payload = payload.get("sources")
    if not isinstance(payload, list):
        raise ValueError(f"Expected a JSON list or {{\"sources\": [...]}} in {path}")
    sources: list[ContentSource] = []
    for item in payload:
        source = ContentSource.model_validate(item)
        location = source.location
        if not location.startswith(("http://", "https://")):
            candidate = Path(location)
            if not candidate.is_absolute():
                location = str((Path(path).resolve().parent / candidate).resolve())
                source = source.model_copy(update={"location": location})
        sources.append(source)
    return sources
