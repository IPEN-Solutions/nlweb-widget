from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ContentSourceKind(str, Enum):
    SCHEMA_JSON = "schema_json"
    WEBPAGE_SCHEMA = "webpage_schema"
    RSS = "rss"
    ATOM = "atom"
    SITEMAP = "sitemap"
    DATABASE = "database"
    CUSTOM = "custom"


class ContentSource(BaseModel):
    model_config = ConfigDict(extra="allow")

    name: str = Field(min_length=1, max_length=200)
    kind: ContentSourceKind
    location: str = Field(min_length=1)
    site: str = "default"
    enabled: bool = True
    replace_site: bool = False
    batch_size: int = Field(default=100, ge=1, le=10_000)
    metadata: dict[str, Any] = Field(default_factory=dict)


class SourceState(BaseModel):
    source: str
    fingerprint: str | None = None
    item_keys: set[str] = Field(default_factory=set)
    last_success: datetime | None = None
    last_attempt: datetime | None = None
    last_status: str | None = None
    last_error: str | None = None
    version: int = 1


class SyncResult(BaseModel):
    source: str
    site: str
    kind: ContentSourceKind
    status: str
    changed: bool = False
    skipped: bool = False
    total_loaded: int = 0
    deleted_count: int = 0
    message: str | None = None
    attempts: int = 1
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    finished_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class SyncSummary(BaseModel):
    started_at: datetime
    finished_at: datetime
    results: list[SyncResult] = Field(default_factory=list)

    @property
    def succeeded(self) -> int:
        return sum(result.status == "ok" for result in self.results)

    @property
    def failed(self) -> int:
        return sum(result.status == "error" for result in self.results)

    @property
    def skipped(self) -> int:
        return sum(result.skipped for result in self.results)
