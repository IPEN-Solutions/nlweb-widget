import pytest

from nlweb_widget import ContentDocument, NLWebRequest, NLWebWidget
from nlweb_widget.settings import NLWebSettings


@pytest.fixture
def enabled_widget() -> NLWebWidget:
    return NLWebWidget(settings=NLWebSettings(_env_file=None, enabled=True))


@pytest.mark.asyncio
async def test_answer_declares_response_type(enabled_widget: NLWebWidget) -> None:
    await enabled_widget.index(
        ContentDocument(
            id="1", url="https://example.test/1", title="One", content="one service"
        )
    )
    response = await enabled_widget.ask(NLWebRequest(query={"text": "one"}))
    assert response.meta["response_type"] == "answer"
    assert response.meta["version"] == "0.55"
    assert response.meta["response_format"] == "conversational_search"


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["generate", "unsupported"])
async def test_unsupported_mode_is_failure(
    enabled_widget: NLWebWidget, mode: str
) -> None:
    response = await enabled_widget.ask(
        NLWebRequest(query={"text": "one"}, prefer={"mode": mode})
    )
    assert response.meta["response_type"] == "failure"
    assert response.error is not None
    assert response.error.code == "UNSUPPORTED_MODE"


@pytest.mark.asyncio
async def test_unsupported_format_is_failure(enabled_widget: NLWebWidget) -> None:
    response = await enabled_widget.ask(
        NLWebRequest(query={"text": "one"}, prefer={"response_format": "unknown"})
    )
    assert response.meta["response_type"] == "failure"
    assert response.error.code == "UNSUPPORTED_FORMAT"


@pytest.mark.asyncio
async def test_no_results_is_failure(enabled_widget: NLWebWidget) -> None:
    response = await enabled_widget.ask(NLWebRequest(query={"text": "missing"}))
    assert response.meta["response_type"] == "failure"
    assert response.error is not None
    assert response.error.code == "NO_RESULTS"


@pytest.mark.asyncio
async def test_empty_query_is_failure(enabled_widget: NLWebWidget) -> None:
    response = await enabled_widget.ask(NLWebRequest(query={"text": "  "}))
    assert response.meta["response_type"] == "failure"
    assert response.error is not None
    assert response.error.code == "INVALID_QUERY"


@pytest.mark.asyncio
async def test_retrieval_error_is_internal_failure() -> None:
    class BrokenStore:
        async def search(self, query: str, limit: int = 10):
            raise RuntimeError("boom")

    widget = NLWebWidget(
        store=BrokenStore(),
        settings=NLWebSettings(_env_file=None, enabled=True),
    )
    response = await widget.ask(NLWebRequest(query={"text": "anything"}))
    assert response.meta["response_type"] == "failure"
    assert response.error is not None
    assert response.error.code == "INTERNAL_ERROR"


@pytest.mark.asyncio
async def test_summarize_mode_emits_typed_result_item_not_top_level_summary(
    enabled_widget: NLWebWidget,
) -> None:
    await enabled_widget.index(
        ContentDocument(
            id="summary-1",
            url="https://example.test/summary",
            title="Summary source",
            content="Authoritative summary source text.",
            schema_object={"@type": "Article", "headline": "Summary source"},
        )
    )
    from nlweb_widget.protocol import protocol_ask

    payload = await protocol_ask(
        enabled_widget,
        NLWebRequest(query={"text": "summary source"}, prefer={"mode": "summarize"}),
    )
    assert "summary" not in payload
    assert payload["results"][0] == {
        "@type": "SearchSummary",
        "text": "Authoritative summary source text.",
    }
    assert payload["results"][1]["@type"] == "Article"
    assert payload["results"][1]["headline"] == "Summary source"
    assert "schema_object" not in payload["results"][1]
    assert "score" not in payload["results"][1]


@pytest.mark.asyncio
async def test_grounding_survives_to_ask_result_without_rewriting(
    enabled_widget: NLWebWidget,
) -> None:
    grounding = {
        "source": "https://example.test/evidence/report.json",
        "description": "Consumer-declared public verification endpoint",
        "custom": {"policy": "retain-exactly"},
    }
    await enabled_widget.index(
        ContentDocument(
            id="grounded-1",
            url="https://example.test/report",
            title="Grounded report",
            content="Evidence report content.",
            schema_object={"@type": "Article", "name": "Grounded report"},
            metadata={"grounding": grounding},
        )
    )
    from nlweb_widget.protocol import protocol_ask

    payload = await protocol_ask(
        enabled_widget, NLWebRequest(query={"text": "evidence report"})
    )
    assert payload["results"][0]["grounding"] == grounding


@pytest.mark.asyncio
async def test_grounding_survives_in_mcp_structured_content(
    enabled_widget: NLWebWidget,
) -> None:
    grounding = {"source": "https://example.test/evidence", "proof": {"ref": "abc"}}
    await enabled_widget.index(
        ContentDocument(
            id="mcp-grounded",
            url="https://example.test/mcp",
            title="MCP grounded",
            content="MCP evidence content.",
            schema_object={"@type": "Article"},
            metadata={"grounding": grounding},
        )
    )
    from nlweb_widget.protocol import protocol_mcp

    payload = await protocol_mcp(
        enabled_widget,
        {
            "jsonrpc": "2.0",
            "id": 42,
            "method": "tools/call",
            "params": {"name": "ask", "arguments": {"query": {"text": "MCP evidence"}}},
        },
    )
    item = payload["result"]["structuredContent"]["results"][0]
    assert item["grounding"] == grounding


@pytest.mark.asyncio
async def test_jsonld_graph_primary_entity_is_projected_as_typed_result(
    enabled_widget: NLWebWidget,
) -> None:
    await enabled_widget.index(
        ContentDocument(
            id="graph-1",
            url="https://example.test/services/ai",
            title="AI Service",
            content="A graph-backed authoritative service.",
            schema_object={
                "@context": "https://schema.org",
                "@graph": [
                    {
                        "@type": "Organization",
                        "@id": "https://example.test/#org",
                        "name": "Example",
                    },
                    {
                        "@type": "Service",
                        "url": "https://example.test/services/ai",
                        "name": "AI Service",
                    },
                ],
            },
        )
    )
    from nlweb_widget.protocol import protocol_ask

    payload = await protocol_ask(
        enabled_widget, NLWebRequest(query={"text": "graph-backed service"})
    )
    result = payload["results"][0]
    assert result["@type"] == "Service"
    assert result["name"] == "AI Service"
    assert "@graph" not in result
    assert result["@context"] == "https://schema.org"


@pytest.mark.asyncio
async def test_conflicting_source_and_metadata_grounding_is_reported_explicitly(
    enabled_widget: NLWebWidget,
) -> None:
    await enabled_widget.index(
        ContentDocument(
            id="grounding-conflict",
            url="https://example.test/conflict",
            title="Grounding conflict",
            content="Grounding conflict test record.",
            schema_object={
                "@type": "Article",
                "grounding": {"source": "https://one.example/"},
            },
            metadata={"grounding": {"source": "https://two.example/"}},
        )
    )
    response = await enabled_widget.ask(
        NLWebRequest(query={"text": "grounding conflict"})
    )
    assert response.meta["response_type"] == "failure"
    assert response.error is not None
    assert response.error.code == "INVALID_SOURCE_METADATA"
    assert "conflicting source and metadata grounding" in (response.error.message or "")


@pytest.mark.asyncio
async def test_streaming_protocol_emits_start_results_and_complete(
    enabled_widget: NLWebWidget,
) -> None:
    from nlweb_widget.protocol import protocol_ask_stream

    await enabled_widget.index(
        ContentDocument(
            id="sse-1",
            url="https://example.test/sse",
            title="SSE service",
            content="SSE protocol streaming test",
            schema_object={"@type": "Service"},
        )
    )
    events = [
        event
        async for event in protocol_ask_stream(
            enabled_widget,
            NLWebRequest(
                query={"text": "SSE protocol"},
                prefer={"streaming": True},
                meta={
                    "version": "0.55",
                    "session_context": {"conversation_id": "sse-qa"},
                },
            ),
        )
    ]
    assert events[0].startswith("event: start\n")
    assert any(event.startswith("event: result\n") for event in events)
    assert events[-1].startswith("event: complete\n")
    assert '"conversation_id":"sse-qa"' in events[-1]


async def test_streaming_yields_start_before_waiting_for_widget_answer() -> None:
    from types import SimpleNamespace

    from nlweb_widget.models import NLWebRequest
    from nlweb_widget.protocol import protocol_ask_stream

    class DelayedWidget:
        def __init__(self):
            self.called = False

        async def ask(self, request):
            self.called = True
            return SimpleNamespace(
                model_dump=lambda **kwargs: {
                    "results": [],
                    "_meta": {"version": "0.55", "response_type": "answer"},
                }
            )

    widget = DelayedWidget()
    stream = protocol_ask_stream(
        widget,
        NLWebRequest.model_validate(
            {"query": {"text": "test"}, "prefer": {"streaming": "true"}}
        ),
    )
    first = await anext(stream)
    assert first.startswith("event: start\n")
    assert widget.called is False
    await stream.aclose()
