from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_serializer, field_validator, model_serializer


class ContentDocument(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str
    url: HttpUrl | str
    title: str
    content: str
    schema_object: dict[str, Any] = Field(default_factory=dict)
    site: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class NLWebQuery(BaseModel):
    """NLWeb query with extensible schema.org/domain filter attributes."""

    text: str
    site: str | None = None
    model_config = ConfigDict(extra="allow")


class NLWebRequest(BaseModel):
    """NLWeb v0.55 request envelope.

    ``query`` is required; ``context``, ``prefer`` and ``meta`` are optional
    extensibility sections. Unknown attributes are retained for forward
    compatibility with domain-specific NLWeb extensions.
    """

    query: NLWebQuery
    context: dict[str, Any] | None = None
    prefer: dict[str, Any] | None = None
    meta: dict[str, Any] | None = None

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "query": {
                        "text": "What AI engineering services are available?",
                        "site": "example",
                    },
                    "context": {},
                    "prefer": {"mode": "list", "response_format": "conversational_search"},
                    "meta": {"version": "0.55"},
                }
            ]
        }
    )

    @field_validator("query", mode="before")
    @classmethod
    def normalize_query(cls, value: Any) -> Any:
        if isinstance(value, str):
            return {"text": value}
        return value


class SearchResult(BaseModel):
    """A protocol result item backed by an authoritative schema object.

    Internal retrieval fields remain available to Python callers, while the
    serializer projects source properties directly into the result item. This
    avoids inventing a nested ``schema_object`` protocol field.
    """

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    url: str | None = None
    name: str | None = None
    site: str | None = None
    score: float | None = None
    description: str | None = None
    schema_object: dict[str, Any] = Field(default_factory=dict, exclude=True)
    schema_type: str | None = Field(default=None, alias="@type")
    text: str | None = None
    grounding: dict[str, Any] | None = None

    @model_serializer(mode="plain")
    def serialize_protocol_item(self) -> dict[str, Any]:
        # SearchSummary is a protocol result item, not a top-level response
        # convenience property. Keep its structure minimal and normative.
        if self.schema_type == "SearchSummary":
            item: dict[str, Any] = {"@type": "SearchSummary", "text": self.text or ""}
            if self.grounding is not None:
                item["grounding"] = self.grounding
            return item

        item = _project_schema_record(self.schema_object, self.name, self.url)
        if self.schema_type and not item.get("@type"):
            item["@type"] = self.schema_type
        if self.name is not None:
            item.setdefault("name", self.name)
        if self.description is not None:
            item.setdefault("description", self.description)
        if self.url:
            item.setdefault("url", self.url)
        if self.grounding is not None:
            item["grounding"] = self.grounding
        # Explicit result-level extension fields are retained, but internal
        # retrieval controls (site/score) are never emitted as domain fields.
        for key, value in self.__pydantic_extra__.items() if self.__pydantic_extra__ else ():
            item.setdefault(key, value)
        return item


def _project_schema_record(
    schema_object: dict[str, Any], name: str | None, url: str | None
) -> dict[str, Any]:
    """Project the primary entity from a JSON-LD graph into one result item."""
    graph = schema_object.get("@graph")
    if not isinstance(graph, list) or schema_object.get("@type"):
        return dict(schema_object)
    records = [record for record in graph if isinstance(record, dict)]
    if not records:
        return dict(schema_object)
    selected = next(
        (record for record in records if url and (record.get("url") == url or record.get("@id") == url)),
        None,
    )
    if selected is None and name:
        selected = next((record for record in records if record.get("name") == name or record.get("headline") == name), None)
    if selected is None:
        selected = next((record for record in records if record.get("@type")), records[0])
    result = dict(selected)
    if "@context" in schema_object:
        result.setdefault("@context", schema_object["@context"])
    return result


class NLWebError(BaseModel):
    code: str
    message: str | None = None


class NLWebResponse(BaseModel):
    """NLWeb v0.55 response envelope.

    ``meta`` serializes as the normative ``_meta`` response field. The
    optional ChatGPT Apps fields are additive and emitted only when that
    response format is requested.
    """

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    query_id: str | None = None
    results: list[SearchResult] = Field(default_factory=list)
    meta: dict[str, Any] = Field(default_factory=dict, alias="_meta")
    error: NLWebError | None = None
    content: list[dict[str, Any]] | None = None
    structured_data: list[dict[str, Any]] | None = Field(
        default=None, alias="structuredData"
    )


class DiscoveryDocument(BaseModel):
    protocol: str = "NLWeb"
    specification: str = "https://nlweb.ai/docs/specification"
    endpoints: dict[str, str] = Field(default_factory=lambda: {"ask": "/ask", "mcp": "/mcp"})
    discovery: str = "/.well-known/nlweb"
    health: str = "/health"


class MCPRequest(BaseModel):
    jsonrpc: Literal["2.0"]
    id: int | str | None = None
    method: str
    params: dict[str, Any] | None = None

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
                {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/call",
                    "params": {
                        "name": "ask",
                        "arguments": {
                            "query": {"text": "What services are available?"},
                            "prefer": {"mode": "list"},
                        },
                    },
                },
            ]
        }
    )
